"""
Attendance: time between signing in and signing out.

This is NOT the same thing as hours/WorkSession, and the separation is
deliberate:

    WorkSession       entered by the administrator. The official record.
    AttendanceSession recorded by the system on login/logout. Evidence.

Keeping them apart means the rule from the original brief still holds - a
member cannot write their own working hours - while Hetansh still gets an
automatic picture of when people were actually online. When the two disagree,
that gap is itself the useful information.

Nobody can edit an AttendanceSession through the app, not even an
administrator. It is a machine record. Corrections belong on the WorkSession.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class AttendanceSessionQuerySet(models.QuerySet):
    def for_user(self, user):
        if user.is_admin_user:
            return self
        return self.filter(member=user)

    def open(self):
        return self.filter(ended_at__isnull=True)

    def closed(self):
        return self.filter(ended_at__isnull=False)

    def on_date(self, day):
        return self.filter(started_at__date=day)

    def between(self, start, end):
        return self.filter(started_at__date__gte=start, started_at__date__lte=end)

    def total_minutes(self):
        return self.aggregate(total=models.Sum("duration_minutes"))["total"] or 0


class AttendanceSession(TimeStampedModel):
    class StartSource(models.TextChoices):
        LOGIN = "LOGIN", "Signed in"
        MANUAL = "MANUAL", "Started manually"

    class EndSource(models.TextChoices):
        LOGOUT = "LOGOUT", "Signed out"
        MANUAL = "MANUAL", "Stopped manually"
        AUTO = "AUTO", "Closed automatically"

    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attendance_sessions"
    )
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=0, editable=False)

    start_source = models.CharField(
        max_length=10, choices=StartSource.choices, default=StartSource.LOGIN
    )
    end_source = models.CharField(max_length=10, choices=EndSource.choices, blank=True)
    auto_closed = models.BooleanField(
        default=False,
        help_text="Nobody signed out - this was closed at the daily cap, so the "
                  "figure is not a real measurement.",
    )

    objects = AttendanceSessionQuerySet.as_manager()

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["member", "-started_at"]),
            models.Index(fields=["ended_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ended_at__isnull=True) | models.Q(ended_at__gte=models.F("started_at")),
                name="attendance_end_after_start",
            ),
            # One running session per person, enforced by the database.
            # start_session() already checks this, but a check-then-insert can
            # lose a race when someone signs in on two devices at the same
            # moment. A partial unique index cannot lose that race, and a
            # duplicate day is exactly the kind of error nobody would notice.
            models.UniqueConstraint(
                fields=["member"],
                condition=models.Q(ended_at__isnull=True),
                name="one_open_attendance_session_per_member",
            ),
        ]

    def __str__(self):
        state = "open" if self.is_open else self.duration_display
        return f"{self.member} {timezone.localtime(self.started_at):%d %b %H:%M} ({state})"

    @property
    def is_open(self):
        return self.ended_at is None

    @property
    def duration_display(self):
        minutes = self.duration_minutes if not self.is_open else self.minutes_so_far
        hours, remainder = divmod(minutes, 60)
        if hours and remainder:
            return f"{hours}h {remainder}m"
        return f"{hours}h" if hours else f"{remainder}m"

    @property
    def minutes_so_far(self):
        """Live elapsed time for a session still running."""
        if not self.is_open:
            return self.duration_minutes
        return max(0, int((timezone.now() - self.started_at).total_seconds() // 60))

    def close(self, when=None, source=EndSource.LOGOUT, auto=False):
        """Idempotent - closing an already-closed session does nothing."""
        if not self.is_open:
            return self
        when = when or timezone.now()
        if when < self.started_at:
            when = self.started_at
        self.ended_at = when
        self.end_source = source
        self.auto_closed = auto
        self.save(update_fields=["ended_at", "end_source", "auto_closed", "duration_minutes", "updated_at"])
        return self

    def save(self, *args, **kwargs):
        # Duration is always derived, never supplied.
        if self.ended_at and self.started_at:
            self.duration_minutes = max(
                0, int((self.ended_at - self.started_at).total_seconds() // 60)
            )
        else:
            self.duration_minutes = 0
        if "update_fields" in kwargs and kwargs["update_fields"] is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"duration_minutes"}
        super().save(*args, **kwargs)
