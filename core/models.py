"""
Shared model building blocks plus the audit log.

core owns no business data of its own beyond ActivityLog. It holds the pieces
every other app reuses, so those apps never import from each other just to
share a base class.
"""

from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    """Adds created_at / updated_at to any model that inherits it."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ActivityLog(models.Model):
    """
    Append-only record of consequential actions.

    Deliberately does NOT use a GenericForeignKey. We store the model name, the
    id and a human-readable string instead, which means:
      * the log survives deletion of whatever it points at
      * reading the log never joins against django_content_type
      * a row is meaningful on its own, even years later

    `actor` is who did it. `subject` is the member it was done *to* - that is
    what lets a member see their own history and lets the admin member-detail
    page show one person's timeline.
    """

    class Verb(models.TextChoices):
        MEMBER_INVITED = "MEMBER_INVITED", "Member invited"
        MEMBER_ACTIVATED = "MEMBER_ACTIVATED", "Member activated"
        MEMBER_UPDATED = "MEMBER_UPDATED", "Member updated"
        MEMBER_DEACTIVATED = "MEMBER_DEACTIVATED", "Member deactivated"
        MEMBER_REACTIVATED = "MEMBER_REACTIVATED", "Member reactivated"
        TASK_CREATED = "TASK_CREATED", "Task created"
        TASK_UPDATED = "TASK_UPDATED", "Task updated"
        TASK_STATUS_CHANGED = "TASK_STATUS_CHANGED", "Task status changed"
        HOURS_ADDED = "HOURS_ADDED", "Work hours added"
        HOURS_UPDATED = "HOURS_UPDATED", "Work hours edited"
        HOURS_DELETED = "HOURS_DELETED", "Work hours deleted"
        FILE_UPLOADED = "FILE_UPLOADED", "File uploaded"
        FILE_DELETED = "FILE_DELETED", "File deleted"
        REPORT_SUBMITTED = "REPORT_SUBMITTED", "Daily report submitted"
        REPORT_UPDATED = "REPORT_UPDATED", "Daily report updated"
        FORM_STATS_RECORDED = "FORM_STATS_RECORDED", "Form statistics recorded"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activities_performed",
    )
    subject = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activities_about",
        help_text="The member this action concerns, if any.",
    )
    verb = models.CharField(max_length=32, choices=Verb.choices)
    target_repr = models.CharField(max_length=255, blank=True)
    target_model = models.CharField(max_length=50, blank=True)
    target_id = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "activity log entry"
        verbose_name_plural = "activity log"
        indexes = [
            models.Index(fields=["subject", "-created_at"]),
            models.Index(fields=["verb", "-created_at"]),
        ]

    def __str__(self):
        actor = self.actor.full_name if self.actor else "System"
        return f"{actor} - {self.get_verb_display()} - {self.target_repr}".strip(" -")
