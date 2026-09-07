"""Daily reports and the Google/Ether integration contracts."""

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from integrations.ether.config import get_ether_client, notify_ether
from integrations.ether.null import NullEtherClient
from integrations.google.client import IntegrationNotConfigured, GoogleSheetsClient, is_configured
from integrations.google.models import FormSubmissionStat, TrackedForm
from integrations.google.services import sync_form_stats

from .models import DailyReport


class DailyReportTests(TestCase):
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

    def test_member_can_file_a_report_for_themselves(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse("reports:create"), {
            "date": timezone.localdate(), "summary": "Cleared the backlog",
            "work_completed": "Processed 47 forms.", "blockers": "", "notes": "",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(DailyReport.objects.get().member, self.member)

    def test_a_report_cannot_be_filed_in_someone_elses_name(self):
        self.client.force_login(self.member)
        self.client.post(reverse("reports:create"), {
            "date": timezone.localdate(), "summary": "x", "work_completed": "y",
            "member": self.other.pk,
        })
        self.assertEqual(DailyReport.objects.get().member, self.member)

    def test_only_one_report_per_member_per_day(self):
        self.client.force_login(self.member)
        payload = {"date": timezone.localdate(), "summary": "First",
                   "work_completed": "x", "blockers": "", "notes": ""}
        self.client.post(reverse("reports:create"), payload)
        self.client.post(reverse("reports:create"), dict(payload, summary="Second"))
        self.assertEqual(DailyReport.objects.count(), 1)

    def test_member_cannot_read_another_members_report(self):
        report = DailyReport.objects.create(
            member=self.other, date=timezone.localdate(), summary="Private", work_completed="x"
        )
        self.client.force_login(self.member)
        self.assertEqual(
            self.client.get(reverse("reports:detail", args=[report.pk])).status_code, 404
        )

    def test_admin_can_read_every_report(self):
        report = DailyReport.objects.create(
            member=self.member, date=timezone.localdate(), summary="Visible", work_completed="x"
        )
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(reverse("reports:detail", args=[report.pk])).status_code, 200
        )

    def test_admin_cannot_rewrite_a_members_report(self):
        """Reading everything is not the same as authoring anything."""
        report = DailyReport.objects.create(
            member=self.member, date=timezone.localdate(), summary="Original", work_completed="x"
        )
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(reverse("reports:edit", args=[report.pk])).status_code, 403
        )


class GoogleIntegrationTests(TestCase):
    """The app must behave normally with no Google credentials at all."""

    def test_integration_is_dormant_by_default(self):
        self.assertFalse(is_configured())

    def test_building_a_client_without_credentials_raises_clearly(self):
        with self.assertRaises(IntegrationNotConfigured):
            GoogleSheetsClient(credentials_path="")

    def test_sync_is_a_no_op_when_dormant_rather_than_an_error(self):
        member = User.objects.create_user(email="s@example.com", password="pw", full_name="S")
        form = TrackedForm.objects.create(member=member, name="Intake form")
        self.assertEqual(sync_form_stats(form), 0)

    @override_settings(GOOGLE_SERVICE_ACCOUNT_FILE="/tmp/fake-credentials.json")
    def test_sync_does_not_crash_when_the_client_is_unimplemented(self):
        member = User.objects.create_user(email="s@example.com", password="pw", full_name="S")
        form = TrackedForm.objects.create(member=member, name="Intake", sheet_id="sheet-123")
        self.assertEqual(sync_form_stats(form), 0)

    def test_manual_statistics_work_without_google(self):
        member = User.objects.create_user(email="s@example.com", password="pw", full_name="S")
        form = TrackedForm.objects.create(member=member, name="Intake")
        FormSubmissionStat.objects.create(
            form=form, date=timezone.localdate(), submission_count=47, verified_count=40
        )
        self.assertEqual(form.total_submissions(), 47)
        self.assertEqual(FormSubmissionStat.objects.get().source, "Manual entry")

    def test_a_member_only_sees_their_own_form_statistics(self):
        mine = User.objects.create_user(email="s@example.com", password="pw", full_name="S")
        theirs = User.objects.create_user(email="j@example.com", password="pw", full_name="J")
        for owner in (mine, theirs):
            form = TrackedForm.objects.create(member=owner, name=f"Form {owner.pk}")
            FormSubmissionStat.objects.create(
                form=form, date=timezone.localdate(), submission_count=5
            )
        self.assertEqual(FormSubmissionStat.objects.for_user(mine).count(), 1)


class EtherIntegrationTests(TestCase):
    """No invented API. The default client does nothing and says so."""

    def test_default_client_is_the_null_client(self):
        self.assertIsInstance(get_ether_client(), NullEtherClient)

    def test_null_client_is_not_live(self):
        self.assertFalse(get_ether_client().is_live)

    def test_sending_an_event_is_harmless_and_reports_failure_honestly(self):
        self.assertFalse(notify_ether("task.completed", {"task_id": 1}))

    def test_status_says_it_is_not_configured(self):
        self.assertFalse(get_ether_client().fetch_status()["configured"])

    @override_settings(ETHER_BASE_URL="https://example.invalid")
    def test_setting_a_url_does_not_fake_a_working_integration(self):
        """Configuring a URL with no implementation must not look like success."""
        client = get_ether_client()
        self.assertIsInstance(client, NullEtherClient)
        self.assertFalse(client.is_live)
