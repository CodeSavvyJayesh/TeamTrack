"""
Attendance: the clock that starts on sign in and stops on sign out.

The cases that matter are the messy ones - forgetting to sign out, signing in
twice, signing out days later. Those are what turn this feature from a useful
signal into misleading numbers, so most of these tests are about them.
"""

from datetime import timedelta

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from .models import AttendanceSession
from .selectors import totals_for
from .services import close_all_stale, end_session, open_session_for, start_session


class ClockOnLoginTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(
            email="member@example.com", password="member-pw-4821", full_name="Member One"
        )

    def test_signing_in_starts_the_clock(self):
        self.assertEqual(AttendanceSession.objects.count(), 0)
        self.client.login(username="member@example.com", password="member-pw-4821")

        session = AttendanceSession.objects.get()
        self.assertEqual(session.member, self.member)
        self.assertTrue(session.is_open)
        self.assertEqual(session.start_source, AttendanceSession.StartSource.LOGIN)

    def test_signing_out_stops_the_clock_and_records_the_duration(self):
        self.client.login(username="member@example.com", password="member-pw-4821")
        session = AttendanceSession.objects.get()

        # Rewind the start so there is measurable time to record.
        session.started_at = timezone.now() - timedelta(hours=2, minutes=30)
        session.save()

        self.client.post(reverse("accounts:logout"))

        session.refresh_from_db()
        self.assertFalse(session.is_open)
        self.assertEqual(session.duration_minutes, 150)
        self.assertEqual(session.duration_display, "2h 30m")
        self.assertFalse(session.auto_closed)

    def test_signing_in_twice_does_not_start_a_second_clock(self):
        """A phone and a laptop must not double-count the same day."""
        self.client.login(username="member@example.com", password="member-pw-4821")
        second_client = self.client_class()
        second_client.login(username="member@example.com", password="member-pw-4821")

        self.assertEqual(AttendanceSession.objects.filter(member=self.member).count(), 1)

    def test_a_failed_login_starts_nothing(self):
        self.client.login(username="member@example.com", password="wrong")
        self.assertEqual(AttendanceSession.objects.count(), 0)

    def test_signing_out_with_no_session_is_harmless(self):
        self.assertIsNone(end_session(self.member))


class ForgottenSignOutTests(TestCase):
    """The failure mode that decides whether these numbers are worth anything."""

    def setUp(self):
        self.member = User.objects.create_user(
            email="member@example.com", password="member-pw-4821", full_name="Member One"
        )

    def _stale_session(self, hours_ago):
        return AttendanceSession.objects.create(
            member=self.member, started_at=timezone.now() - timedelta(hours=hours_ago)
        )

    @override_settings(ATTENDANCE_MAX_HOURS=9)
    def test_a_forgotten_session_is_capped_not_left_to_grow(self):
        self._stale_session(hours_ago=40)
        closed = close_all_stale()

        self.assertEqual(closed, 1)
        session = AttendanceSession.objects.get()
        self.assertFalse(session.is_open)
        self.assertTrue(session.auto_closed)
        self.assertEqual(session.duration_minutes, 9 * 60)  # capped, not 40 hours
        self.assertEqual(session.end_source, AttendanceSession.EndSource.AUTO)

    @override_settings(ATTENDANCE_MAX_HOURS=9)
    def test_a_session_within_the_cap_is_left_alone(self):
        self._stale_session(hours_ago=3)
        self.assertEqual(close_all_stale(), 0)
        self.assertTrue(AttendanceSession.objects.get().is_open)

    @override_settings(ATTENDANCE_MAX_HOURS=9)
    def test_signing_in_next_morning_closes_yesterdays_forgotten_session(self):
        yesterday = self._stale_session(hours_ago=20)
        self.client.login(username="member@example.com", password="member-pw-4821")

        yesterday.refresh_from_db()
        self.assertTrue(yesterday.auto_closed)
        self.assertEqual(yesterday.duration_minutes, 9 * 60)
        # And today's is a fresh, honest session.
        self.assertEqual(AttendanceSession.objects.filter(ended_at__isnull=True).count(), 1)

    @override_settings(ATTENDANCE_MAX_HOURS=9)
    def test_signing_out_days_later_does_not_award_a_40_hour_day(self):
        self._stale_session(hours_ago=40)
        end_session(self.member)

        session = AttendanceSession.objects.get()
        self.assertTrue(session.auto_closed)
        self.assertEqual(session.duration_minutes, 9 * 60)

    def test_closing_an_already_closed_session_changes_nothing(self):
        session = self._stale_session(hours_ago=2)
        session.close()
        first_end = session.ended_at

        session.close()
        session.refresh_from_db()
        self.assertEqual(session.ended_at, first_end)


class StopForTheDayTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(
            email="member@example.com", password="member-pw-4821", full_name="Member One"
        )

    def test_member_can_stop_without_signing_out(self):
        self.client.login(username="member@example.com", password="member-pw-4821")
        session = AttendanceSession.objects.get()
        session.started_at = timezone.now() - timedelta(hours=1)
        session.save()

        response = self.client.post(reverse("attendance:stop"))
        self.assertEqual(response.status_code, 302)

        session.refresh_from_db()
        self.assertFalse(session.is_open)
        self.assertEqual(session.end_source, AttendanceSession.EndSource.MANUAL)
        self.assertFalse(session.auto_closed)

        # Still signed in afterwards - stopping the clock is not signing out.
        self.assertEqual(self.client.get(reverse("dashboard:member")).status_code, 200)


class AttendanceVisibilityTests(TestCase):
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
        for user in (self.member, self.other):
            AttendanceSession.objects.create(
                member=user,
                started_at=timezone.now() - timedelta(hours=2),
                ended_at=timezone.now(),
            )

    def test_member_sees_only_their_own_attendance(self):
        # force_login fires the same signal a real login does, so this member
        # also picks up a live session. Everything listed must still be theirs.
        self.client.force_login(self.member)
        sessions = self.client.get(reverse("attendance:list")).context["sessions"]
        self.assertTrue(sessions)
        self.assertEqual({s.member_id for s in sessions}, {self.member.pk})

    def test_admin_sees_the_whole_team(self):
        self.client.force_login(self.admin)
        sessions = self.client.get(reverse("attendance:list")).context["sessions"]
        member_ids = {s.member_id for s in sessions}
        self.assertIn(self.member.pk, member_ids)
        self.assertIn(self.other.pk, member_ids)

    def test_anonymous_visitor_is_sent_to_login(self):
        response = self.client.get(reverse("attendance:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_totals_are_per_member(self):
        totals = totals_for(self.member)
        self.assertEqual(totals["today"], 120)

    def test_attendance_is_separate_from_recorded_hours(self):
        """
        The original rule still holds: tracked time is NOT working hours.

        A member with two hours of attendance still has zero recorded hours
        until an administrator enters them.
        """
        from hours.models import WorkSession
        from hours.selectors import totals_for as recorded_totals_for

        self.assertEqual(WorkSession.objects.filter(member=self.member).count(), 0)
        self.assertEqual(recorded_totals_for(self.member)["today"], 0)
        self.assertEqual(totals_for(self.member)["today"], 120)

    def test_members_cannot_edit_attendance_anywhere(self):
        """There is no edit or delete endpoint at all - by design."""
        from django.urls import NoReverseMatch

        for name in ("attendance:edit", "attendance:delete", "attendance:create"):
            with self.assertRaises(NoReverseMatch):
                reverse(name)


class EdgeCaseRegressionTests(TestCase):
    """Cases found by deliberately trying to break it after the build."""

    def setUp(self):
        self.member = User.objects.create_user(
            email="member@example.com", password="member-pw-4821", full_name="Member One"
        )

    def test_the_database_refuses_a_second_open_session(self):
        """
        start_session() checks first, but a check-then-insert can lose a race
        when two devices sign in at the same instant. The constraint cannot.
        """
        from django.db import IntegrityError, transaction

        AttendanceSession.objects.create(member=self.member, started_at=timezone.now())
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AttendanceSession.objects.create(member=self.member, started_at=timezone.now())

    def test_a_closed_session_does_not_block_a_new_one(self):
        first = AttendanceSession.objects.create(
            member=self.member, started_at=timezone.now() - timedelta(hours=3)
        )
        first.close()
        AttendanceSession.objects.create(member=self.member, started_at=timezone.now())
        self.assertEqual(AttendanceSession.objects.filter(member=self.member).count(), 2)

    def test_two_members_can_both_be_signed_in(self):
        other = User.objects.create_user(email="o@x.com", password="pw", full_name="Other")
        AttendanceSession.objects.create(member=self.member, started_at=timezone.now())
        AttendanceSession.objects.create(member=other, started_at=timezone.now())
        self.assertEqual(AttendanceSession.objects.open().count(), 2)
