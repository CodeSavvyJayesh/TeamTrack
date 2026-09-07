"""
Work hours.

The most permission-sensitive model in the project. Two rules matter:

  1. A member never creates or edits their own hours. Enforced in the views
     (AdminRequiredMixin + AdminOnlyWriteMixin), not in the template.
  2. duration_minutes is never supplied by a form. It is recomputed in save()
     from start_time and end_time every single time, so it cannot drift away
     from the times it claims to summarise.
"""

from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.models import TimeStampedModel


class WorkSessionQuerySet(models.QuerySet):
    def for_user(self, user):
        if user.is_admin_user:
            return self
        return self.filter(member=user)

    def total_minutes(self):
        return self.aggregate(total=models.Sum("duration_minutes"))["total"] or 0

    def on(self, day):
        return self.filter(date=day)

    def between(self, start, end):
        return self.filter(date__gte=start, date__lte=end)


class WorkSession(TimeStampedModel):
    """One continuous stretch of work on one day, entered by an administrator."""

    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="work_sessions"
    )
    date = models.DateField(db_index=True, default=timezone.localdate)
    start_time = models.TimeField()
    end_time = models.TimeField()
    duration_minutes = models.PositiveIntegerField(editable=False, default=0)
    note = models.CharField(max_length=255, blank=True)

    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    objects = WorkSessionQuerySet.as_manager()

    class Meta:
        ordering = ["-date", "-start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["member", "date", "start_time"], name="unique_member_date_start"
            ),
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="end_time_after_start_time",
            ),
        ]
        indexes = [models.Index(fields=["member", "-date"])]

    def __str__(self):
        return f"{self.member} {self.date} {self.start_time:%H:%M}-{self.end_time:%H:%M}"

    # --- duration ---------------------------------------------------------

    @staticmethod
    def calculate_minutes(start_time, end_time):
        """
        10:00 -> 16:30 gives 390.

        Overnight shifts are out of scope for v1 (see ARCHITECTURE.md, L4):
        end_time must be later than start_time on the same date.
        """
        if not start_time or not end_time:
            return 0
        reference = datetime(2000, 1, 1)
        delta = datetime.combine(reference, end_time) - datetime.combine(reference, start_time)
        if delta < timedelta(0):
            return 0
        return int(delta.total_seconds() // 60)

    def clean(self):
        super().clean()
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({"end_time": "End time must be later than start time."})

        if self.member_id and self.date and self.start_time and self.end_time:
            clash = (
                WorkSession.objects.filter(member_id=self.member_id, date=self.date)
                .exclude(pk=self.pk)
                .filter(start_time__lt=self.end_time, end_time__gt=self.start_time)
            )
            if clash.exists():
                raise ValidationError(
                    "This overlaps another session already recorded for this member on this date."
                )

    def save(self, *args, **kwargs):
        self.duration_minutes = self.calculate_minutes(self.start_time, self.end_time)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("hours:list")

    @property
    def duration_display(self):
        hours, minutes = divmod(self.duration_minutes, 60)
        if hours and minutes:
            return f"{hours}h {minutes}m"
        return f"{hours}h" if hours else f"{minutes}m"
