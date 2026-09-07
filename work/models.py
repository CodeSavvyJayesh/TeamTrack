"""
Generic task management.

Nothing here knows what kind of work a member does. A Project is whatever
container makes sense for that person - a codebase, a campaign, a research
topic - and a Task is a unit of work assigned to exactly one member.
"""

from django.conf import settings
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
        return self.open().filter(due_date__lt=timezone.localdate())


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
    def is_overdue(self):
        return (
            self.due_date is not None
            and self.status != self.Status.COMPLETED
            and self.due_date < timezone.localdate()
        )
