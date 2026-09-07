"""Administrator-only member management, plus the dashboard routing rules."""

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from accounts.models import Invitation, User
from core.models import ActivityLog


class AdminAccessTests(TestCase):
    """Every administrative URL must be closed to a member."""

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

    def test_member_is_blocked_from_every_admin_url(self):
        self.client.force_login(self.member)
        admin_urls = [
            reverse("members:list"),
            reverse("members:invite"),
            reverse("members:invitations"),
            reverse("members:detail", args=[self.other.pk]),
            reverse("members:edit", args=[self.other.pk]),
            reverse("dashboard:admin"),
            reverse("dashboard:activity"),
            reverse("hours:create"),
            reverse("work:task_create"),
            reverse("work:project_list"),
        ]
        for url in admin_urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_member_cannot_deactivate_anyone(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse("members:toggle_active", args=[self.other.pk]))
        self.assertEqual(response.status_code, 403)
        self.other.refresh_from_db()
        self.assertTrue(self.other.is_active)

    def test_admin_reaches_the_team_dashboard(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("dashboard:admin")).status_code, 200)

    def test_dashboard_router_sends_each_role_to_its_own_page(self):
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.get(reverse("dashboard:home")), reverse("dashboard:admin"))

        self.client.force_login(self.member)
        self.assertRedirects(self.client.get(reverse("dashboard:home")), reverse("dashboard:member"))


class InvitationFlowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin@example.com", password="admin-pw-9931", full_name="Admin"
        )
        self.client.force_login(self.admin)

    def test_inviting_creates_a_record_and_sends_one_email(self):
        response = self.client.post(reverse("members:invite"), {
            "full_name": "New Person", "email": "newbie@example.com",
            "work_type": "Operations", "department": "",
        })
        self.assertEqual(response.status_code, 302)

        invitation = Invitation.objects.get()
        self.assertEqual(invitation.invited_by, self.admin)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(invitation.token, mail.outbox[0].body)

    def test_inviting_is_recorded_in_the_activity_log(self):
        self.client.post(reverse("members:invite"), {
            "full_name": "New Person", "email": "newbie@example.com",
            "work_type": "", "department": "",
        })
        self.assertTrue(
            ActivityLog.objects.filter(verb=ActivityLog.Verb.MEMBER_INVITED).exists()
        )

    def test_cannot_invite_an_email_that_already_has_an_account(self):
        User.objects.create_user(email="taken@example.com", password="pw", full_name="Taken")
        response = self.client.post(reverse("members:invite"), {
            "full_name": "Duplicate", "email": "taken@example.com",
            "work_type": "", "department": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Invitation.objects.count(), 0)

    def test_cannot_send_two_pending_invitations_to_one_address(self):
        payload = {"full_name": "New Person", "email": "newbie@example.com",
                   "work_type": "", "department": ""}
        self.client.post(reverse("members:invite"), payload)
        self.client.post(reverse("members:invite"), payload)
        self.assertEqual(Invitation.objects.count(), 1)

    def test_resending_issues_a_new_token(self):
        self.client.post(reverse("members:invite"), {
            "full_name": "New Person", "email": "newbie@example.com",
            "work_type": "", "department": "",
        })
        invitation = Invitation.objects.get()
        old_token = invitation.token

        self.client.post(reverse("members:invitation_resend", args=[invitation.pk]))
        invitation.refresh_from_db()
        self.assertNotEqual(invitation.token, old_token)
        self.assertEqual(len(mail.outbox), 2)


class DeactivationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin@example.com", password="admin-pw-9931", full_name="Admin"
        )
        self.member = User.objects.create_user(
            email="member@example.com", password="member-pw-4821", full_name="Member"
        )

    def test_deactivating_keeps_the_record_and_blocks_login(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("members:toggle_active", args=[self.member.pk]))

        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)
        self.assertTrue(User.objects.filter(pk=self.member.pk).exists())

        self.client.logout()
        self.assertFalse(self.client.login(username="member@example.com", password="member-pw-4821"))

    def test_reactivating_restores_access(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("members:toggle_active", args=[self.member.pk]))
        self.client.post(reverse("members:toggle_active", args=[self.member.pk]))

        self.member.refresh_from_db()
        self.assertTrue(self.member.is_active)
