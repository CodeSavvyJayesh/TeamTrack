"""Tasks: creation, assignment, status changes, and who may do which."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from .models import Project, Task


class TaskModelTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="h@example.com", password="pw", full_name="H")
        self.member = User.objects.create_user(email="s@example.com", password="pw", full_name="S")

    def _task(self, **overrides):
        defaults = {
            "title": "Write the report",
            "assigned_to": self.member,
            "created_by": self.admin,
        }
        defaults.update(overrides)
        return Task.objects.create(**defaults)

    def test_new_tasks_start_pending_with_no_completion_time(self):
        task = self._task()
        self.assertEqual(task.status, Task.Status.PENDING)
        self.assertIsNone(task.completed_at)

    def test_completing_a_task_stamps_completed_at(self):
        task = self._task()
        task.status = Task.Status.COMPLETED
        task.save()
        self.assertIsNotNone(task.completed_at)

    def test_reopening_a_task_clears_completed_at(self):
        task = self._task(status=Task.Status.COMPLETED)
        self.assertIsNotNone(task.completed_at)
        task.status = Task.Status.IN_PROGRESS
        task.save()
        self.assertIsNone(task.completed_at)

    def test_overdue_only_applies_to_unfinished_work(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        overdue = self._task(due_date=yesterday)
        self.assertTrue(overdue.is_overdue)

        done = self._task(title="Done", due_date=yesterday, status=Task.Status.COMPLETED)
        self.assertFalse(done.is_overdue)

    def test_for_user_scopes_to_the_assignee(self):
        other = User.objects.create_user(email="j@example.com", password="pw", full_name="J")
        mine = self._task()
        theirs = self._task(title="Theirs", assigned_to=other)

        self.assertEqual(list(Task.objects.for_user(self.member)), [mine])
        self.assertEqual(set(Task.objects.for_user(self.admin)), {mine, theirs})


class TaskPermissionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin@example.com", password="admin-pw-9931", full_name="Admin"
        )
        self.member = User.objects.create_user(
            email="member@example.com", password="member-pw-4821", full_name="Member"
        )
        self.other = User.objects.create_user(
            email="other@example.com", password="other-pw-4821", full_name="Other"
        )
        self.task = Task.objects.create(
            title="My task", assigned_to=self.member, created_by=self.admin
        )
        self.foreign_task = Task.objects.create(
            title="Not mine", assigned_to=self.other, created_by=self.admin
        )

    def test_member_cannot_create_a_task(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("work:task_create")).status_code, 403)

    def test_member_cannot_edit_a_task(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("work:task_edit", args=[self.task.pk]))
        self.assertEqual(response.status_code, 403)

    def test_member_cannot_open_another_members_task(self):
        """404, not 403 - a 403 would confirm the task exists."""
        self.client.force_login(self.member)
        response = self.client.get(reverse("work:task_detail", args=[self.foreign_task.pk]))
        self.assertEqual(response.status_code, 404)

    def test_member_can_change_status_on_their_own_task(self):
        self.client.force_login(self.member)
        response = self.client.post(
            reverse("work:task_status", args=[self.task.pk]), {"status": Task.Status.COMPLETED}
        )
        self.assertEqual(response.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.COMPLETED)

    def test_member_cannot_change_status_on_another_members_task(self):
        self.client.force_login(self.member)
        response = self.client.post(
            reverse("work:task_status", args=[self.foreign_task.pk]),
            {"status": Task.Status.COMPLETED},
        )
        self.assertEqual(response.status_code, 404)
        self.foreign_task.refresh_from_db()
        self.assertEqual(self.foreign_task.status, Task.Status.PENDING)

    def test_status_endpoint_cannot_reassign_a_task(self):
        """The member form exposes only `status`, so extra POST keys are ignored."""
        self.client.force_login(self.member)
        self.client.post(reverse("work:task_status", args=[self.task.pk]), {
            "status": Task.Status.IN_PROGRESS,
            "assigned_to": self.other.pk,
            "priority": Task.Priority.URGENT,
            "title": "Renamed by a member",
        })
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.IN_PROGRESS)
        self.assertEqual(self.task.assigned_to, self.member)
        self.assertEqual(self.task.priority, Task.Priority.MEDIUM)
        self.assertEqual(self.task.title, "My task")

    def test_admin_can_create_and_assign(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("work:task_create"), {
            "title": "New assignment", "description": "",
            "assigned_to": self.member.pk, "status": Task.Status.PENDING,
            "priority": Task.Priority.HIGH, "notes": "",
        })
        self.assertEqual(response.status_code, 302)
        created = Task.objects.get(title="New assignment")
        self.assertEqual(created.assigned_to, self.member)
        self.assertEqual(created.created_by, self.admin)

    def test_member_list_only_shows_their_own_tasks(self):
        self.client.force_login(self.member)
        tasks = self.client.get(reverse("work:task_list")).context["tasks"]
        self.assertEqual(list(tasks), [self.task])

    def test_member_cannot_reach_projects(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("work:project_list")).status_code, 403)
