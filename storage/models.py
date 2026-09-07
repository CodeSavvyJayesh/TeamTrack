"""
Uploaded files.

Only metadata lives in the database. The bytes go to MEDIA_ROOT under a
randomised path, and every download is served by a permission-checked view -
MEDIA_URL is never exposed by the web server in production.
"""

import os
import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.models import TimeStampedModel


def upload_path(instance, filename):
    """
    uploads/2026/09/<user id>/<random>.<ext>

    The stored name is random so that a guessed URL cannot be constructed from
    a known filename, and so two people uploading "report.xlsx" never collide.
    The human-readable name is kept in `original_name`.
    """
    extension = os.path.splitext(filename)[1].lower()[:10]
    today = timezone.localdate()
    return f"uploads/{today:%Y/%m}/{instance.uploaded_by_id}/{uuid.uuid4().hex}{extension}"


class UploadedFileQuerySet(models.QuerySet):
    def visible_to(self, user):
        """
        The single definition of who may see which file.

        Admin sees everything. A member sees their own files plus anything
        explicitly shared with the team. ADMIN_ONLY files are never listed to a
        member, even their own - that is the point of the setting.
        """
        if user.is_admin_user:
            return self
        own_but_not_admin_only = models.Q(uploaded_by=user) & ~models.Q(
            visibility=UploadedFile.Visibility.ADMIN_ONLY
        )
        shared_with_team = models.Q(visibility=UploadedFile.Visibility.TEAM)
        return self.filter(own_but_not_admin_only | shared_with_team).distinct()


class UploadedFile(TimeStampedModel):
    class Visibility(models.TextChoices):
        PRIVATE = "PRIVATE", "Private (me and administrators)"
        TEAM = "TEAM", "Team (everyone can see it)"
        ADMIN_ONLY = "ADMIN_ONLY", "Administrators only"

    file = models.FileField(upload_to=upload_path)
    original_name = models.CharField(max_length=255, editable=False)
    content_type = models.CharField(max_length=100, blank=True, editable=False)
    size_bytes = models.PositiveBigIntegerField(default=0, editable=False)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="uploads"
    )
    description = models.CharField(max_length=255, blank=True)
    related_task = models.ForeignKey(
        "work.Task", on_delete=models.SET_NULL, null=True, blank=True, related_name="files"
    )
    project = models.ForeignKey(
        "work.Project", on_delete=models.SET_NULL, null=True, blank=True, related_name="files"
    )
    visibility = models.CharField(
        max_length=12, choices=Visibility.choices, default=Visibility.PRIVATE
    )

    objects = UploadedFileQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["uploaded_by", "-created_at"])]

    def __str__(self):
        return self.original_name

    def get_absolute_url(self):
        return reverse("storage:download", args=[self.pk])

    def may_be_read_by(self, user):
        if user.is_admin_user:
            return True
        if self.visibility == self.Visibility.ADMIN_ONLY:
            return False
        return self.uploaded_by_id == user.pk or self.visibility == self.Visibility.TEAM

    def may_be_deleted_by(self, user):
        return user.is_admin_user or self.uploaded_by_id == user.pk

    @property
    def extension(self):
        return os.path.splitext(self.original_name)[1].lower().lstrip(".")

    @property
    def size_display(self):
        size = float(self.size_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"
