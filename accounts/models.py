"""
Identity: who can log in, what kind of work they do, and how they got here.

Three models:
  User          - authentication + the authoritative role flag
  MemberProfile - work-related attributes, one per user, created by signal
  Invitation    - a signed-in-advance, expiring ticket to create an account

Why User and MemberProfile are separate: User is swapped in via
AUTH_USER_MODEL and is painful to migrate. Keeping work attributes in a
separate table means adding "shift_pattern" later is an ordinary migration on
an ordinary model.
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.urls import reverse
from django.utils import timezone


class UserManager(BaseUserManager):
    """Email is the identifier, so the stock username-based manager won't do."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)  # hashed, never stored in the clear
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.MEMBER)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)

    def members(self):
        return self.filter(role=User.Role.MEMBER)

    def admins(self):
        return self.filter(role=User.Role.ADMIN)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Login is by email. There is no username field.

    `role` is the app's authorization flag and is what every permission check
    reads. `is_staff` / `is_superuser` are left to mean exactly what Django
    means by them - access to /django-admin/ - and nothing more.
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrator"
        MEMBER = "MEMBER", "Member"

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)

    is_active = models.BooleanField(
        default=True,
        help_text="Unticking this deactivates the account. Their records are kept.",
    )
    is_staff = models.BooleanField(default=False, help_text="Access to /django-admin/.")
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name or self.email

    def save(self, *args, **kwargs):
        self.email = self.email.lower().strip()
        super().save(*args, **kwargs)

    # Django calls these in a few places (admin, auth templates).
    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name.split(" ")[0] if self.full_name else self.email

    @property
    def is_admin_user(self):
        """The single source of truth for 'may see everything'."""
        return self.role == self.Role.ADMIN

    @property
    def initials(self):
        parts = [p for p in self.full_name.split(" ") if p]
        if not parts:
            return self.email[:2].upper()
        return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()

    def get_absolute_url(self):
        return reverse("members:detail", args=[self.pk])


class MemberProfile(models.Model):
    """
    Work-related attributes. Created automatically for every user by a signal,
    so `user.profile` is always safe to access.

    `tracks_google_forms` is the switch that decides whether the Google Forms
    module appears for this person at all. That is how the app supports members
    whose work has nothing to do with forms without any code branching on names.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    work_type = models.CharField(
        max_length=100,
        blank=True,
        help_text="Free text, e.g. Operations, Developer, Research, Design.",
    )
    department = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    joined_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, help_text="Administrator notes. Not shown to the member.")
    tracks_google_forms = models.BooleanField(
        default=False,
        verbose_name="Tracks Google Forms",
        help_text="Show Google Forms metrics for this member.",
    )

    class Meta:
        verbose_name = "member profile"

    def __str__(self):
        return f"Profile: {self.user}"


class InvitationQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(accepted_at__isnull=True, expires_at__gt=timezone.now())

    def expired(self):
        return self.filter(accepted_at__isnull=True, expires_at__lte=timezone.now())

    def accepted(self):
        return self.filter(accepted_at__isnull=False)


def default_expiry():
    return timezone.now() + timedelta(days=settings.INVITATION_EXPIRY_DAYS)


def generate_token():
    return secrets.token_urlsafe(32)


class Invitation(models.Model):
    """
    A one-time ticket to create an account.

    Only the random token is stored. No password ever touches this table - the
    invited person sets their own, hashed by Django, when they accept.
    """

    email = models.EmailField()
    full_name = models.CharField(max_length=150)
    work_type = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)
    tracks_google_forms = models.BooleanField(default=False)

    token = models.CharField(max_length=64, unique=True, default=generate_token, editable=False)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="invitations_sent"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=default_expiry)
    accepted_at = models.DateTimeField(null=True, blank=True)

    objects = InvitationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["token"])]

    def __str__(self):
        return f"Invitation for {self.email}"

    def save(self, *args, **kwargs):
        self.email = self.email.lower().strip()
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return self.expires_at <= timezone.now()

    @property
    def is_accepted(self):
        return self.accepted_at is not None

    @property
    def is_valid(self):
        return not self.is_accepted and not self.is_expired

    @property
    def status(self):
        if self.is_accepted:
            return "Accepted"
        return "Expired" if self.is_expired else "Pending"

    def get_accept_url(self, request=None):
        path = reverse("accounts:invitation_accept", args=[self.token])
        return request.build_absolute_uri(path) if request else path

    def refresh_token(self):
        """Used when an admin resends an expired invitation."""
        self.token = generate_token()
        self.expires_at = default_expiry()
        self.save(update_fields=["token", "expires_at"])
