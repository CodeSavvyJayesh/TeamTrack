from django.core.mail import EmailMessage
from django.test import TestCase, override_settings
from unittest.mock import patch
import json, urllib.error, io

from core.email import BrevoAPIBackend, _split_address


class SplitAddressTests(TestCase):
    def test_plain_address(self):
        self.assertEqual(_split_address("a@b.com"), {"email": "a@b.com"})

    def test_named_address(self):
        self.assertEqual(
            _split_address("TeamTrack <no-reply@b.com>"),
            {"name": "TeamTrack", "email": "no-reply@b.com"},
        )


@override_settings(
    EMAIL_BACKEND="core.email.BrevoAPIBackend",
    BREVO_API_KEY="test-key",
    DEFAULT_FROM_EMAIL="TeamTrack <no-reply@x.com>",
)
class BrevoBackendTests(TestCase):
    def _message(self):
        return EmailMessage(
            subject="You have been invited",
            body="Click here: https://x/accept/abc",
            from_email=None,
            to=["new@example.com"],
        )

    def test_it_posts_the_message_to_brevo(self):
        captured = {}

        class FakeResponse:
            status = 201
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["key"] = request.get_header("Api-key")
            captured["body"] = json.loads(request.data.decode())
            return FakeResponse()

        with patch("core.email.urllib.request.urlopen", fake_urlopen):
            sent = BrevoAPIBackend().send_messages([self._message()])

        self.assertEqual(sent, 1)
        self.assertEqual(captured["url"], "https://api.brevo.com/v3/smtp/email")
        self.assertEqual(captured["key"], "test-key")
        self.assertEqual(captured["body"]["to"], [{"email": "new@example.com"}])
        self.assertEqual(captured["body"]["sender"]["email"], "no-reply@x.com")
        self.assertIn("accept/abc", captured["body"]["textContent"])

    def test_a_refusal_raises_when_not_silent(self):
        error = urllib.error.HTTPError(
            "u", 401, "Unauthorized", {}, io.BytesIO(b'{"message":"bad key"}')
        )
        with patch("core.email.urllib.request.urlopen", side_effect=error):
            with self.assertRaises(urllib.error.HTTPError):
                BrevoAPIBackend().send_messages([self._message()])

    def test_a_refusal_is_swallowed_when_silent(self):
        error = urllib.error.HTTPError(
            "u", 401, "Unauthorized", {}, io.BytesIO(b'{"message":"bad key"}')
        )
        with patch("core.email.urllib.request.urlopen", side_effect=error):
            self.assertEqual(
                BrevoAPIBackend(fail_silently=True).send_messages([self._message()]), 0
            )
