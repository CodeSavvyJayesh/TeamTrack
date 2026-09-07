"""
Working hours.

This module carries the single most important rule in the brief:
a member may look at their hours and may never change them.
"""

from datetime import time, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from .models import WorkSession
from .selectors import totals_for


class DurationCalculationTests(TestCase):
    def test_the_example_from_the_brief(self):
        """10:00 to 16:30 is 6h 30m."""
        self.assertEqual(WorkSession.calculate_minutes(time(10, 0), time(16, 30)), 390)

    def test_whole_hours(self):
        self.assertEqual(WorkSession.calculate_minutes(time(9, 0), time(17, 0)), 480)

    def test_minutes_only(self):
        self.assertEqual(WorkSession.calculate_minutes(time(9, 0), time(9, 45)), 45)

    def test_duration_is_recomputed_on_every_save(self):
        admin = User.objects.create_superuser(email="h@example.com", password="pw", full_name="H")
        member = User.objects.create_user(email="s@example.com", password="pw", full_name="S")

        session = WorkSession.objects.create(
            member=member, date=timezone.localdate(),
            start_time=time(10, 0), end_time=time(16, 30), entered_by=admin,
        )
        self.assertEqual(session.duration_minutes, 390)
        self.assertEqual(session.duration_display, "6h 30m")

        # Even if something sets the field directly, save() overwrites it.
        session.duration_minutes = 9999
        session.end_time = time(12, 0)
        session.save()
        self.assertEqual(session.duration_minutes, 120)


class WorkSessionValidationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="h@example.com", password="pw", full_name="H")
        self.member = User.objects.create_user(email="s@example.com", password="pw", full_name="S")
        self.today = timezone.localdate()

    def test_end_before_start_is_rejected(self):
        session = WorkSession(
            member=self.member, date=self.today,
            start_time=time(16, 0), end_time=time(10, 0), entered_by=self.admin,
        )
        with self.assertRaises(ValidationError):
            session.clean()

    def test_overlapping_sessions_are_rejected(self):
        WorkSession.objects.create(
            member=self.member, date=self.today,
            start_time=time(10, 0), end_time=time(14, 0), entered_by=self.admin,
        )
        overlapping = WorkSession(
            member=self.member, date=self.today,
            start_time=time(13, 0), end_time=time(17, 0), entered_by=self.admin,
        )
        with self.assertRaises(ValidationError):
            overlapping.clean()

    def test_adjacent_sessions_are_allowed(self):
        WorkSession.objects.create(
            member=self.member, date=self.today,
            start_time=time(10, 0), end_time=time(14, 0), entered_by=self.admin,
        )
        adjacent = WorkSession(
            member=self.member, date=self.today,
            start_time=time(14, 0), end_time=time(17, 0), entered_by=self.admin,
        )
        adjacent.clean()  # must not raise

    def test_two_members_can_work_the_same_shift(self):
        other = User.objects.create_user(email="j@example.com", password="pw", full_name="J")
        WorkSession.objects.create(
            member=self.member, date=self.today,
            start_time=time(10, 0), end_time=time(14, 0), entered_by=self.admin,
        )
        same_shift = WorkSession(
            member=other, date=self.today,
            start_time=time(10, 0), end_time=time(14, 0), entered_by=self.admin,
        )
        same_shift.clean()  # must not raise


class WorkHourPermissionTests(TestCase):
    """The rule: Hetansh writes, members read."""

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
        self.today = timezone.localdate()
        self.session = WorkSession.objects.create(
            member=self.member, date=self.today,
            start_time=time(10, 0), end_time=time(16, 30), entered_by=self.admin,
        )

    # --- writes ----------------------------------------------------------

    def test_member_cannot_open_the_add_hours_page(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("hours:create")).status_code, 403)

    def test_member_cannot_post_new_hours(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse("hours:create"), {
            "member": self.member.pk, "date": self.today,
            "start_time": "09:00", "end_time": "18:00",
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(WorkSession.objects.count(), 1)

    def test_member_cannot_edit_their_own_hours(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse("hours:edit", args=[self.session.pk]), {
            "member": self.member.pk, "date": self.today,
            "start_time": "06:00", "end_time": "23:00",
        })
        self.assertEqual(response.status_code, 403)
        self.session.refresh_from_db()
        self.assertEqual(self.session.duration_minutes, 390)

    def test_member_cannot_delete_hours(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse("hours:delete", args=[self.session.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(WorkSession.objects.filter(pk=self.session.pk).exists())

    def test_admin_can_add_hours(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("hours:create"), {
            "member": self.other.pk, "date": self.today,
            "start_time": "09:00", "end_time": "17:30", "note": "",
        })
        self.assertEqual(response.status_code, 302)
        created = WorkSession.objects.get(member=self.other)
        self.assertEqual(created.duration_minutes, 510)
        self.assertEqual(created.entered_by, self.admin)

    def test_admin_can_correct_a_mistake(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("hours:edit", args=[self.session.pk]), {
            "member": self.member.pk, "date": self.today,
            "start_time": "10:00", "end_time": "15:00", "note": "Corrected",
        })
        self.assertEqual(response.status_code, 302)
        self.session.refresh_from_db()
        self.assertEqual(self.session.duration_minutes, 300)
        self.assertEqual(self.session.updated_by, self.admin)

    # --- reads -----------------------------------------------------------

    def test_member_can_read_their_own_hours(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("hours:list"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.session, response.context["sessions"])

    def test_member_cannot_see_another_members_hours(self):
        WorkSession.objects.create(
            member=self.other, date=self.today,
            start_time=time(9, 0), end_time=time(12, 0), entered_by=self.admin,
        )
        self.client.force_login(self.member)
        sessions = self.client.get(reverse("hours:list")).context["sessions"]
        self.assertEqual([s.member_id for s in sessions], [self.member.pk])

    def test_admin_sees_everyone(self):
        WorkSession.objects.create(
            member=self.other, date=self.today,
            start_time=time(9, 0), end_time=time(12, 0), entered_by=self.admin,
        )
        self.client.force_login(self.admin)
        self.assertEqual(len(self.client.get(reverse("hours:list")).context["sessions"]), 2)


class TotalsTests(TestCase):
    def test_daily_weekly_and_monthly_totals(self):
        admin = User.objects.create_superuser(email="h@example.com", password="pw", full_name="H")
        member = User.objects.create_user(email="s@example.com", password="pw", full_name="S")
        today = timezone.localdate()

        WorkSession.objects.create(
            member=member, date=today, start_time=time(10, 0), end_time=time(16, 30), entered_by=admin
        )
        yesterday = today - timedelta(days=1)
        WorkSession.objects.create(
            member=member, date=yesterday, start_time=time(9, 0), end_time=time(12, 0), entered_by=admin
        )

        totals = totals_for(member, today)
        self.assertEqual(totals["today"], 390)
        # Yesterday only counts toward the week if it is in the same week.
        expected_week = 390 if today.weekday() == 0 else 570
        self.assertEqual(totals["week"], expected_week)
