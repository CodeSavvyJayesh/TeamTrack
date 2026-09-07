"""
Google Forms tracking.

The important property of this module: the rest of the app reads
FormSubmissionStat rows and does not care where they came from. Today an
administrator can type them in. Later, `sync_form_stats` fills the same rows
from Google Sheets. No dashboard, template or view changes when that happens.

If GOOGLE_SERVICE_ACCOUNT_FILE is unset, nothing here does anything and the
application runs exactly as if this app were not installed.
"""

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.models import TimeStampedModel


class TrackedForm(TimeStampedModel):
    """One Google Form whose submission counts we care about."""

    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tracked_forms"
    )
    name = models.CharField(max_length=150)
    google_form_id = models.CharField(
        max_length=120,
        blank=True,
        help_text="Leave blank until Google is connected. Statistics can still be entered by hand.",
    )
    sheet_id = models.CharField(
        max_length=120, blank=True, help_text="The responses spreadsheet, once available."
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "tracked form"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("google_forms:list")

    @property
    def is_connected(self):
        return bool(self.google_form_id or self.sheet_id)

    def total_submissions(self):
        return self.stats.aggregate(total=models.Sum("submission_count"))["total"] or 0


class FormSubmissionStatQuerySet(models.QuerySet):
    def for_user(self, user):
        if user.is_admin_user:
            return self
        return self.filter(form__member=user)

    def total_submissions(self):
        return self.aggregate(total=models.Sum("submission_count"))["total"] or 0


class FormSubmissionStat(models.Model):
    """Submission counts for one form on one day."""

    form = models.ForeignKey(TrackedForm, on_delete=models.CASCADE, related_name="stats")
    date = models.DateField(default=timezone.localdate, db_index=True)
    submission_count = models.PositiveIntegerField(default=0)
    verified_count = models.PositiveIntegerField(
        default=0, help_text="Of those submissions, how many have been checked."
    )
    synced_at = models.DateTimeField(
        null=True, blank=True, help_text="Set when a row came from Google rather than by hand."
    )

    objects = FormSubmissionStatQuerySet.as_manager()

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["form", "date"], name="one_stat_per_form_per_day")
        ]

    def __str__(self):
        return f"{self.form} {self.date}: {self.submission_count}"

    @property
    def source(self):
        return "Google sync" if self.synced_at else "Manual entry"
