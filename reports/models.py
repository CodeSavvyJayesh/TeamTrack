"""
Daily reports.

Written by the member, read by the member and by administrators. The fields
are deliberately loose free text: a developer's report and an operations
report have nothing structurally in common, and forcing a schema on them would
break the "members do different kinds of work" rule.
"""

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.models import TimeStampedModel


class DailyReportQuerySet(models.QuerySet):
    def for_user(self, user):
        if user.is_admin_user:
            return self
        return self.filter(member=user)


class DailyReport(TimeStampedModel):
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="daily_reports"
    )
    date = models.DateField(default=timezone.localdate, db_index=True)
    summary = models.CharField(max_length=255, help_text="One line: what today was about.")
    work_completed = models.TextField(help_text="What you finished.")
    blockers = models.TextField(blank=True, help_text="Anything stopping you. Leave blank if none.")
    notes = models.TextField(blank=True)
    related_tasks = models.ManyToManyField("work.Task", blank=True, related_name="reports")

    objects = DailyReportQuerySet.as_manager()

    class Meta:
        ordering = ["-date", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["member", "date"], name="one_report_per_member_per_day")
        ]
        indexes = [models.Index(fields=["member", "-date"])]

    def __str__(self):
        return f"{self.member} - {self.date}"

    def get_absolute_url(self):
        return reverse("reports:detail", args=[self.pk])

    @property
    def has_blockers(self):
        return bool(self.blockers.strip())
