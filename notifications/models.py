"""
In-app notifications.

Deliberately simple: one row per thing a person needs to know about, with a URL
to click through to. Like ActivityLog it stores model name + id + a display
string rather than a GenericForeignKey, so a notification stays readable even
after whatever it points at is gone.

ActivityLog and Notification look similar but answer different questions:
  ActivityLog  - what happened, for the record. Admin-facing, append-only.
  Notification - what someone still needs to look at. Personal, and dismissable.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class NotificationQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(recipient=user)

    def unread(self):
        return self.filter(read_at__isnull=True)

    def mark_all_read(self):
        return self.unread().update(read_at=timezone.now())


class Notification(models.Model):
    class Kind(models.TextChoices):
        TASK_ASSIGNED = "TASK_ASSIGNED", "New assignment"
        TASK_REASSIGNED = "TASK_REASSIGNED", "Assignment moved to you"
        TASK_UPDATED = "TASK_UPDATED", "Assignment updated"
        TASK_DUE_SOON = "TASK_DUE_SOON", "Deadline approaching"
        HOURS_RECORDED = "HOURS_RECORDED", "Working hours recorded"
        GENERAL = "GENERAL", "Notice"

    ICON = {
        Kind.TASK_ASSIGNED: "i-check",
        Kind.TASK_REASSIGNED: "i-check",
        Kind.TASK_UPDATED: "i-check",
        Kind.TASK_DUE_SOON: "i-clock",
        Kind.HOURS_RECORDED: "i-clock",
        Kind.GENERAL: "i-doc",
    }

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.GENERAL)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    url = models.CharField(
        max_length=255, blank=True, help_text="Where clicking this notification goes."
    )
    target_model = models.CharField(max_length=50, blank=True)
    target_id = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    emailed = models.BooleanField(
        default=False, help_text="Whether an email was also sent for this."
    )

    objects = NotificationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "read_at", "-created_at"])]

    def __str__(self):
        return f"{self.recipient}: {self.title}"

    @property
    def is_read(self):
        return self.read_at is not None

    @property
    def icon(self):
        return self.ICON.get(self.kind, "i-doc")

    def mark_read(self):
        if self.read_at is None:
            self.read_at = timezone.now()
            self.save(update_fields=["read_at"])
