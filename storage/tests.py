"""File uploads, validation and the download permission boundary."""

import os
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User

from .models import UploadedFile

TEMP_MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class FileTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)
        super().tearDownClass()

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

    def _upload(self, name="report.csv", content=b"a,b,c\n1,2,3\n"):
        return SimpleUploadedFile(name, content, content_type="text/csv")

    # --- upload ----------------------------------------------------------

    def test_member_can_upload_and_metadata_is_captured(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse("storage:upload"), {
            "file": self._upload(), "description": "Weekly numbers",
            "visibility": UploadedFile.Visibility.PRIVATE,
        })
        self.assertEqual(response.status_code, 302)

        uploaded = UploadedFile.objects.get()
        self.assertEqual(uploaded.original_name, "report.csv")
        self.assertEqual(uploaded.uploaded_by, self.member)
        self.assertGreater(uploaded.size_bytes, 0)

    def test_disallowed_extension_is_rejected(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse("storage:upload"), {
            "file": SimpleUploadedFile("evil.exe", b"MZ", content_type="application/octet-stream"),
            "visibility": UploadedFile.Visibility.PRIVATE,
        })
        self.assertEqual(response.status_code, 200)  # redisplayed with an error
        self.assertEqual(UploadedFile.objects.count(), 0)

    @override_settings(MAX_UPLOAD_SIZE_BYTES=10, MAX_UPLOAD_SIZE_MB=0)
    def test_oversized_file_is_rejected(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse("storage:upload"), {
            "file": self._upload(content=b"x" * 500),
            "visibility": UploadedFile.Visibility.PRIVATE,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(UploadedFile.objects.count(), 0)

    def test_member_cannot_mark_a_file_admin_only(self):
        """ADMIN_ONLY is an administrative classification, not a member's to apply."""
        self.client.force_login(self.member)
        self.client.post(reverse("storage:upload"), {
            "file": self._upload(), "visibility": UploadedFile.Visibility.ADMIN_ONLY,
        })
        self.assertEqual(UploadedFile.objects.count(), 0)

    # --- visibility ------------------------------------------------------

    def _make_file(self, owner, visibility=UploadedFile.Visibility.PRIVATE):
        return UploadedFile.objects.create(
            file=self._upload(), original_name="report.csv",
            size_bytes=12, uploaded_by=owner, visibility=visibility,
        )

    def test_owner_can_download_their_private_file(self):
        uploaded = self._make_file(self.member)
        self.client.force_login(self.member)
        response = self.client.get(reverse("storage:download", args=[uploaded.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_another_member_cannot_download_a_private_file(self):
        uploaded = self._make_file(self.member)
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get(reverse("storage:download", args=[uploaded.pk])).status_code, 404
        )

    def test_team_files_are_downloadable_by_everyone(self):
        uploaded = self._make_file(self.member, UploadedFile.Visibility.TEAM)
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get(reverse("storage:download", args=[uploaded.pk])).status_code, 200
        )

    def test_admin_can_download_anything(self):
        uploaded = self._make_file(self.member)
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(reverse("storage:download", args=[uploaded.pk])).status_code, 200
        )

    def test_admin_only_files_are_hidden_even_from_their_uploader(self):
        uploaded = self._make_file(self.member, UploadedFile.Visibility.ADMIN_ONLY)
        self.assertFalse(uploaded.may_be_read_by(self.member))
        self.assertTrue(uploaded.may_be_read_by(self.admin))

    def test_list_does_not_leak_other_members_private_files(self):
        self._make_file(self.member)
        self._make_file(self.other)
        self.client.force_login(self.member)
        files = self.client.get(reverse("storage:list")).context["files"]
        self.assertEqual([f.uploaded_by_id for f in files], [self.member.pk])

    def test_member_cannot_delete_someone_elses_file(self):
        uploaded = self._make_file(self.other)
        self.client.force_login(self.member)
        self.assertEqual(
            self.client.post(reverse("storage:delete", args=[uploaded.pk])).status_code, 403
        )
        self.assertTrue(UploadedFile.objects.filter(pk=uploaded.pk).exists())

    def test_anonymous_visitor_cannot_download(self):
        uploaded = self._make_file(self.member)
        response = self.client.get(reverse("storage:download", args=[uploaded.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class SecurityRegressionTests(TestCase):
    """Fixes found in the post-build audit. These must not regress."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin@example.com", password="admin-pw-9931", full_name="Admin"
        )
        self.member = User.objects.create_user(
            email="member@example.com", password="member-pw-4821", full_name="Member"
        )

    def test_task_detail_hides_admin_only_attachments(self):
        """
        A member opening their own task must not see the filename of an
        ADMIN_ONLY file attached to it. The download was always refused; the
        name itself used to leak.
        """
        from work.models import Task

        task = Task.objects.create(
            title="Review", assigned_to=self.member, created_by=self.admin
        )
        UploadedFile.objects.create(
            file=SimpleUploadedFile("secret.csv", b"x"),
            original_name="CONFIDENTIAL-salary-review.csv",
            size_bytes=1,
            uploaded_by=self.admin,
            related_task=task,
            visibility=UploadedFile.Visibility.ADMIN_ONLY,
        )
        self.client.force_login(self.member)
        response = self.client.get(reverse("work:task_detail", args=[task.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "CONFIDENTIAL-salary-review.csv")

    def test_deleting_a_file_removes_it_from_disk(self):
        uploaded = UploadedFile.objects.create(
            file=SimpleUploadedFile("gone.txt", b"bytes"),
            original_name="gone.txt", size_bytes=5, uploaded_by=self.member,
        )
        path = uploaded.file.path
        self.assertTrue(os.path.exists(path))
        uploaded.delete()
        self.assertFalse(os.path.exists(path))

    def test_setup_page_is_not_public(self):
        response = self.client.get(reverse("core:setup_check"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("core:setup_check")).status_code, 403)

        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("core:setup_check")).status_code, 200)

    def test_anonymous_visitor_is_redirected_not_403d(self):
        """A logged-out admin should get the login page, not a bare 403."""
        response = self.client.get(reverse("members:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_signed_in_member_still_gets_403(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("members:list")).status_code, 403)
