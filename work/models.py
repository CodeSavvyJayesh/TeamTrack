"""
Generic task management.

Nothing here knows what kind of work a member does. A Project is whatever
container makes sense for that person - a codebase, a campaign, a research
topic - and a Task is a unit of work assigned to exactly one member.
"""

from datetime import datetime, time
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.models import TimeStampedModel


class Project(TimeStampedModel):
    """An optional grouping for tasks and files. Deliberately thin."""

    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="projects_created"
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("work:project_list")


class TaskQuerySet(models.QuerySet):
    def for_user(self, user):
        """The one place that decides which tasks a person may see."""
        if user.is_admin_user:
            return self
        return self.filter(assigned_to=user)

    def open(self):
        return self.exclude(status=Task.Status.COMPLETED)

    def completed(self):
        return self.filter(status=Task.Status.COMPLETED)

    def overdue(self):
        """
        Past the deadline and not finished.

        A task due today at 17:00 is late at 17:01; one due today with no time
        set is not late until tomorrow. Both cases in one query.
        """
        now = timezone.now()
        today = timezone.localdate()
        return self.open().filter(
            models.Q(due_date__lt=today)
            | models.Q(due_date=today, due_time__isnull=False, due_time__lt=now.time())
        )


class Task(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        COMPLETED = "COMPLETED", "Completed"
        BLOCKED = "BLOCKED", "Blocked"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    # Bootstrap badge class per value, kept next to the choices so a template
    # never has to branch on a status string.
    STATUS_BADGE = {
        Status.PENDING: "secondary",
        Status.IN_PROGRESS: "primary",
        Status.COMPLETED: "success",
        Status.BLOCKED: "danger",
    }
    PRIORITY_BADGE = {
        Priority.LOW: "light text-dark border",
        Priority.MEDIUM: "info",
        Priority.HIGH: "warning text-dark",
        Priority.URGENT: "danger",
    }

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tasks"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tasks_created"
    )
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    due_date = models.DateField(null=True, blank=True)
    due_time = models.TimeField(
        null=True, blank=True,
        help_text="Optional. Leave blank and the deadline is the end of that day.",
    )
    estimated_hours = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.25")), MaxValueValidator(Decimal("999"))],
        help_text="Roughly how long this should take, e.g. 6 for 'finish in 6 hours'.",
    )
    completed_at = models.DateTimeField(null=True, blank=True, editable=False)
    notes = models.TextField(blank=True)

    objects = TaskQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["assigned_to", "status"]),
            models.Index(fields=["status", "due_date"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # completed_at is derived from status, never entered by hand, and is
        # cleared again if a task is reopened.
        if self.status == self.Status.COMPLETED and self.completed_at is None:
            self.completed_at = timezone.now()
        elif self.status != self.Status.COMPLETED:
            self.completed_at = None
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("work:task_detail", args=[self.pk])

    @property
    def status_badge(self):
        return self.STATUS_BADGE.get(self.status, "secondary")

    @property
    def priority_badge(self):
        return self.PRIORITY_BADGE.get(self.priority, "secondary")

    @property
    def deadline_at(self):
        """
        The deadline as a real moment in time.

        A date with no time means end of that day, not midnight at the start of
        it - otherwise a task due "today" is already late the moment it is
        created, which is how most homegrown trackers get this wrong.
        """
        if self.due_date is None:
            return None
        moment = datetime.combine(self.due_date, self.due_time or time(23, 59))
        return timezone.make_aware(moment) if timezone.is_naive(moment) else moment

    @property
    def deadline_display(self):
        if self.due_date is None:
            return ""
        if self.due_time:
            return f"{self.due_date:%d %b %Y} at {self.due_time:%H:%M}"
        return f"{self.due_date:%d %b %Y}"

    @property
    def estimated_hours_display(self):
        if self.estimated_hours is None:
            return ""
        hours = float(self.estimated_hours)
        whole = int(hours)
        minutes = int(round((hours - whole) * 60))
        if whole and minutes:
            return f"{whole}h {minutes}m"
        return f"{whole}h" if whole else f"{minutes}m"

    @property
    def is_overdue(self):
        deadline = self.deadline_at
        return (
            deadline is not None
            and self.status != self.Status.COMPLETED
            and deadline < timezone.now()
        )

    @property
    def hours_until_deadline(self):
        """Negative once the deadline has passed. None if there isn't one."""
        deadline = self.deadline_at
        if deadline is None:
            return None
        return (deadline - timezone.now()).total_seconds() / 3600
