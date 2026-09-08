"""
Notifications, and the assignment flow that produces them.

The requirement being pinned here: Hetansh posts an assignment with a deadline,
and that person is told about it - in the app and by email.
"""

from datetime import time, timedelta

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from work.models import Task

from .models import Notification


class TaskAssignmentNotificationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin@example.com", password="admin-pw-9931", full_name="Hetansh D"
        )
        self.member = User.objects.create_user(
            email="member@example.com", password="member-pw-4821", full_name="Member One"
        )
        self.other = User.objects.create_user(
            email="other@example.com", password="other-pw-4821", full_name="Other Person"
        )
        self.client.force_login(self.admin)
        mail.outbox = []

    def _assign(self, **overrides):
        payload = {
            "title": "Prepare the client report",
            "description": "Pull the numbers and write it up.",
            "assigned_to": self.member.pk,
            "status": Task.Status.PENDING,
            "priority": Task.Priority.HIGH,
            "due_date": (timezone.localdate() + timedelta(days=1)).isoformat(),
            "due_time": "17:00",
            "estimated_hours": "6",
            "notes": "",
        }
        payload.update(overrides)
        return self.client.post(reverse("work:task_create"), payload)

    def test_assigning_notifies_the_person_in_app(self):
        self._assign()

        notification = Notification.objects.get()
        self.assertEqual(notification.recipient, self.member)
        self.assertEqual(notification.kind, Notification.Kind.TASK_ASSIGNED)
        self.assertIn("Prepare the client report", notification.title)
        self.assertFalse(notification.is_read)

    def test_the_notification_carries_the_deadline(self):
        self._assign()
        notification = Notification.objects.get()
        self.assertIn("17:00", notification.body)
        self.assertIn("6h", notification.body)

    def test_assigning_emails_the_person_too(self):
        self._assign()
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["member@example.com"])
        self.assertIn("Prepare the client report", message.subject)
        self.assertIn("17:00", message.body)

    def test_the_notification_links_to_the_task(self):
        self._assign()
        task = Task.objects.get()
        notification = Notification.objects.get()
        self.assertEqual(notification.url, reverse("work:task_detail", args=[task.pk]))
        self.assertEqual(notification.target_model, "Task")
        self.assertEqual(notification.target_id, task.pk)

    def test_nobody_else_is_notified(self):
        self._assign()
        self.assertEqual(Notification.objects.filter(recipient=self.other).count(), 0)
        self.assertEqual(Notification.objects.filter(recipient=self.admin).count(), 0)

    def test_reassigning_notifies_the_new_person(self):
        self._assign()
        task = Task.objects.get()
        mail.outbox = []
        Notification.objects.all().delete()

        self.client.post(reverse("work:task_edit", args=[task.pk]), {
            "title": task.title, "description": task.description,
            "assigned_to": self.other.pk, "status": task.status,
            "priority": task.priority, "notes": "",
        })

        notification = Notification.objects.get()
        self.assertEqual(notification.recipient, self.other)
        self.assertEqual(notification.kind, Notification.Kind.TASK_REASSIGNED)
        self.assertEqual(len(mail.outbox), 1)

    def test_editing_without_reassigning_does_not_ping_anyone(self):
        """Fixing a typo should not send an email."""
        self._assign()
        task = Task.objects.get()
        mail.outbox = []
        Notification.objects.all().delete()

        self.client.post(reverse("work:task_edit", args=[task.pk]), {
            "title": "Prepare the client report (v2)", "description": task.description,
            "assigned_to": self.member.pk, "status": task.status,
            "priority": task.priority, "notes": "",
        })

        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)


class DeadlineTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin@example.com", password="pw", full_name="Admin"
        )
        self.member = User.objects.create_user(
            email="member@example.com", password="pw", full_name="Member"
        )

    def _task(self, **overrides):
        defaults = {"title": "T", "assigned_to": self.member, "created_by": self.admin}
        defaults.update(overrides)
        return Task.objects.create(**defaults)

    def test_a_task_due_today_with_no_time_is_not_late_yet(self):
        """
        The bug most homegrown trackers ship: due_date == today compared against
        midnight, so a task is overdue the moment it is created.
        """
        task = self._task(due_date=timezone.localdate())
        self.assertFalse(task.is_overdue)
        self.assertNotIn(task, Task.objects.overdue())

    def test_a_task_due_yesterday_is_late(self):
        task = self._task(due_date=timezone.localdate() - timedelta(days=1))
        self.assertTrue(task.is_overdue)
        self.assertIn(task, Task.objects.overdue())

    def test_a_deadline_time_that_has_passed_makes_it_late_today(self):
        task = self._task(due_date=timezone.localdate(), due_time=time(0, 1))
        self.assertTrue(task.is_overdue)

    def test_a_completed_task_is_never_overdue(self):
        task = self._task(
            due_date=timezone.localdate() - timedelta(days=5), status=Task.Status.COMPLETED
        )
        self.assertFalse(task.is_overdue)

    def test_estimated_hours_display(self):
        self.assertEqual(self._task(estimated_hours=6).estimated_hours_display, "6h")
        self.assertEqual(self._task(title="B", estimated_hours="1.5").estimated_hours_display, "1h 30m")

    def test_deadline_display_includes_the_time_when_set(self):
        task = self._task(due_date=timezone.localdate(), due_time=time(17, 0))
        self.assertIn("17:00", task.deadline_display)


class NotificationAccessTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(
            email="member@example.com", password="pw", full_name="Member"
        )
        self.other = User.objects.create_user(
            email="other@example.com", password="pw", full_name="Other"
        )
        self.mine = Notification.objects.create(recipient=self.member, title="Mine")
        self.theirs = Notification.objects.create(recipient=self.other, title="Theirs")

    def test_list_shows_only_your_own(self):
        self.client.force_login(self.member)
        notifications = self.client.get(reverse("notifications:list")).context["notifications"]
        self.assertEqual(list(notifications), [self.mine])

    def test_you_cannot_open_someone_elses_notification(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("notifications:open", args=[self.theirs.pk]))
        self.assertEqual(response.status_code, 404)
        self.theirs.refresh_from_db()
        self.assertFalse(self.theirs.is_read)

    def test_opening_marks_it_read_and_forwards(self):
        self.mine.url = "/tasks/"
        self.mine.save()
        self.client.force_login(self.member)

        response = self.client.get(reverse("notifications:open", args=[self.mine.pk]))
        self.assertRedirects(response, "/tasks/", fetch_redirect_response=False)
        self.mine.refresh_from_db()
        self.assertTrue(self.mine.is_read)

    def test_mark_all_read_only_touches_your_own(self):
        self.client.force_login(self.member)
        self.client.post(reverse("notifications:read_all"))

        self.mine.refresh_from_db()
        self.theirs.refresh_from_db()
        self.assertTrue(self.mine.is_read)
        self.assertFalse(self.theirs.is_read)

    def test_unread_count_reaches_every_page(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("dashboard:member"))
        self.assertEqual(response.context["notification_unread_count"], 1)


class EstimateValidationTests(TestCase):
    """A negative estimate used to be accepted straight into the database."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin@example.com", password="pw", full_name="Admin"
        )
        self.member = User.objects.create_user(
            email="member@example.com", password="pw", full_name="Member"
        )
        self.client.force_login(self.admin)

    def _post(self, hours):
        return self.client.post(reverse("work:task_create"), {
            "title": "Estimate check", "description": "", "assigned_to": self.member.pk,
            "status": Task.Status.PENDING, "priority": Task.Priority.LOW,
            "estimated_hours": hours, "notes": "",
        })

    def test_a_negative_estimate_is_rejected(self):
        response = self._post("-5")
        self.assertEqual(response.status_code, 200)  # form redisplayed
        self.assertFalse(Task.objects.filter(title="Estimate check").exists())

    def test_a_zero_estimate_is_rejected(self):
        self._post("0")
        self.assertFalse(Task.objects.filter(title="Estimate check").exists())

    def test_a_sensible_estimate_is_accepted(self):
        self._post("6.5")
        task = Task.objects.get(title="Estimate check")
        self.assertEqual(task.estimated_hours_display, "6h 30m")

    def test_no_estimate_is_fine(self):
        self._post("")
        self.assertTrue(Task.objects.filter(title="Estimate check").exists())
