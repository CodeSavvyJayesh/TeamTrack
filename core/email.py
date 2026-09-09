"""
Sending mail over HTTPS instead of SMTP.

Railway, Render, Fly and most other managed hosts block outbound SMTP ports
(25, 465, 587) to stop their networks being used for spam. The symptom is
`ConnectionRefusedError: [Errno 111] Connection refused` the moment Django
tries to open a connection - no amount of correcting the credentials helps,
because the packets never leave the container.

The fix is to send through a provider's HTTP API on port 443, which is not
blocked. This backend talks to Brevo's transactional endpoint using nothing
but the standard library, so it adds no dependency.

Turn it on by setting BREVO_API_KEY. Leave it unset and Django keeps using
whatever EMAIL_BACKEND is configured.
"""

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import sanitize_address

logger = logging.getLogger(__name__)

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


def _split_address(address):
    """'TeamTrack <no-reply@x.com>' -> {'name': 'TeamTrack', 'email': '...'}."""
    address = sanitize_address(address, "utf-8")
    if "<" in address and address.endswith(">"):
        name, _, email = address.rpartition("<")
        return {"name": name.strip().strip('"'), "email": email[:-1].strip()}
    return {"email": address.strip()}


class BrevoAPIBackend(BaseEmailBackend):
    """
    Minimal transactional sender. Plain-text bodies only, which is all this
    application sends.

    Honours fail_silently exactly like Django's SMTP backend: raise by default,
    swallow when the caller asked to. Returns the number of messages accepted.
    """

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = getattr(settings, "BREVO_API_KEY", "")
        self.timeout = getattr(settings, "EMAIL_TIMEOUT", 10)

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not self.api_key:
            if not self.fail_silently:
                raise ValueError("BREVO_API_KEY is not set.")
            return 0

        sent = 0
        for message in email_messages:
            if self._send(message):
                sent += 1
        return sent

    def _payload(self, message):
        recipients = [_split_address(address) for address in message.to]
        payload = {
            "sender": _split_address(message.from_email or settings.DEFAULT_FROM_EMAIL),
            "to": recipients,
            "subject": message.subject,
            "textContent": message.body or " ",
        }
        if message.cc:
            payload["cc"] = [_split_address(a) for a in message.cc]
        if message.bcc:
            payload["bcc"] = [_split_address(a) for a in message.bcc]
        if message.reply_to:
            payload["replyTo"] = _split_address(message.reply_to[0])
        return payload

    def _send(self, message):
        if not message.to:
            return False

        request = urllib.request.Request(
            BREVO_ENDPOINT,
            data=json.dumps(self._payload(message)).encode("utf-8"),
            headers={
                "api-key": self.api_key,
                "content-type": "application/json",
                "accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return 200 <= response.status < 300
        except urllib.error.HTTPError as error:
            # Brevo explains refusals in the body - an unverified sender, a
            # bad key. Log it; that message is the whole diagnosis.
            detail = error.read().decode("utf-8", "replace")[:500]
            logger.error("Brevo refused the message (HTTP %s): %s", error.code, detail)
            if not self.fail_silently:
                raise
            return False
        except Exception:
            logger.exception("Could not reach Brevo")
            if not self.fail_silently:
                raise
            return False
