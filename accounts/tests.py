"""
Authentication and invitations.

These tests exist to catch a specific class of regression: someone loosening a
permission or an invitation check during a later refactor.
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Invitation, User


class UserModelTests(TestCase):
    def test_email_is_normalised_and_lowercased(self):
        user = User.objects.create_user(email="  Shifa@Example.COM ", password="pw", full_name="Shifa")
        self.assertEqual(user.email, "shifa@example.com")

    def test_password_is_hashed_never_stored_plain(self):
        user = User.objects.create_user(email="a@example.com", password="secret-pw-123", full_name="A")
        self.assertNotEqual(user.password, "secret-pw-123")
        self.assertTrue(user.check_password("secret-pw-123"))

    def test_members_are_not_admins_by_default(self):
        user = User.objects.create_user(email="m@example.com", password="pw", full_name="M")
        self.assertEqual(user.role, User.Role.MEMBER)
        self.assertFalse(user.is_admin_user)

    def test_superuser_is_an_admin(self):
        admin = User.objects.create_superuser(email="h@example.com", password="pw", full_name="H")
        self.assertTrue(admin.is_admin_user)

    def test_profile_is_created_automatically(self):
        user = User.objects.create_user(email="p@example.com", password="pw", full_name="P")
        self.assertIsNotNone(user.profile)
        self.assertFalse(user.profile.tracks_google_forms)


class LoginTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(
            email="member@example.com", password="strong-pw-4821", full_name="Member One"
        )

    def test_valid_login_succeeds(self):
        ok = self.client.login(username="member@example.com", password="strong-pw-4821")
        self.assertTrue(ok)

    def test_wrong_password_is_rejected(self):
        self.assertFalse(self.client.login(username="member@example.com", password="wrong"))

    def test_deactivated_member_cannot_log_in(self):
        self.member.is_active = False
        self.member.save()
        self.assertFalse(self.client.login(username="member@example.com", password="strong-pw-4821"))

    def test_anonymous_visitor_is_redirected_to_login(self):
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)


class InvitationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin@example.com", password="admin-pw-9931", full_name="Admin"
        )

    def _make_invitation(self, **overrides):
        defaults = {
            "email": "newbie@example.com",
            "full_name": "New Person",
            "work_type": "Operations",
            "invited_by": self.admin,
        }
        defaults.update(overrides)
        return Invitation.objects.create(**defaults)

    def test_token_is_generated_and_unique(self):
        first = self._make_invitation()
        second = self._make_invitation(email="other@example.com")
        self.assertTrue(first.token)
        self.assertNotEqual(first.token, second.token)

    def test_fresh_invitation_is_valid(self):
        invitation = self._make_invitation()
        self.assertTrue(invitation.is_valid)
        self.assertEqual(invitation.status, "Pending")

    def test_expired_invitation_is_not_valid(self):
        invitation = self._make_invitation(expires_at=timezone.now() - timedelta(days=1))
        self.assertFalse(invitation.is_valid)
        self.assertEqual(invitation.status, "Expired")

    def test_accepting_creates_an_active_member(self):
        invitation = self._make_invitation()
        url = reverse("accounts:invitation_accept", args=[invitation.token])

        response = self.client.post(
            url, {"password1": "brand-new-pw-77", "password2": "brand-new-pw-77"}
        )
        self.assertEqual(response.status_code, 302)

        user = User.objects.get(email="newbie@example.com")
        self.assertTrue(user.is_active)
        self.assertEqual(user.role, User.Role.MEMBER)
        self.assertEqual(user.profile.work_type, "Operations")
        self.assertTrue(user.check_password("brand-new-pw-77"))

        invitation.refresh_from_db()
        self.assertTrue(invitation.is_accepted)

    def test_a_token_cannot_be_used_twice(self):
        invitation = self._make_invitation()
        url = reverse("accounts:invitation_accept", args=[invitation.token])
        self.client.post(url, {"password1": "brand-new-pw-77", "password2": "brand-new-pw-77"})

        response = self.client.get(url)
        self.assertRedirects(response, reverse("accounts:invitation_invalid"))
        self.assertEqual(User.objects.filter(email="newbie@example.com").count(), 1)

    def test_expired_token_cannot_create_an_account(self):
        invitation = self._make_invitation(expires_at=timezone.now() - timedelta(days=1))
        url = reverse("accounts:invitation_accept", args=[invitation.token])

        self.client.post(url, {"password1": "brand-new-pw-77", "password2": "brand-new-pw-77"})
        self.assertFalse(User.objects.filter(email="newbie@example.com").exists())

    def test_unknown_token_is_rejected(self):
        response = self.client.get(reverse("accounts:invitation_accept", args=["not-a-real-token"]))
        self.assertRedirects(response, reverse("accounts:invitation_invalid"))

    def test_accepting_cannot_set_your_own_role(self):
        """A crafted POST must not be able to smuggle in role=ADMIN."""
        invitation = self._make_invitation()
        url = reverse("accounts:invitation_accept", args=[invitation.token])

        self.client.post(url, {
            "password1": "brand-new-pw-77",
            "password2": "brand-new-pw-77",
            "role": "ADMIN",
            "is_staff": "true",
        })
        user = User.objects.get(email="newbie@example.com")
        self.assertEqual(user.role, User.Role.MEMBER)
        self.assertFalse(user.is_staff)


class ProfileTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(
            email="member@example.com", password="strong-pw-4821", full_name="Member One"
        )
        self.member.profile.work_type = "Research"
        self.member.profile.save()
        self.client.force_login(self.member)

    def test_member_can_edit_their_own_name_and_phone(self):
        response = self.client.post(
            reverse("accounts:profile_edit"), {"full_name": "Member Renamed", "phone": "0123456789"}
        )
        self.assertEqual(response.status_code, 302)
        self.member.refresh_from_db()
        self.assertEqual(self.member.full_name, "Member Renamed")
        self.assertEqual(self.member.profile.phone, "0123456789")

    def test_member_cannot_change_their_own_work_type(self):
        """work_type is administrative. It isn't on the form, so a POST is ignored."""
        self.client.post(reverse("accounts:profile_edit"), {
            "full_name": "Member One", "phone": "", "work_type": "Administrator",
            "tracks_google_forms": "on",
        })
        self.member.profile.refresh_from_db()
        self.assertEqual(self.member.profile.work_type, "Research")
        self.assertFalse(self.member.profile.tracks_google_forms)
