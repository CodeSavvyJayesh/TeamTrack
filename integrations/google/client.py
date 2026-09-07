"""
The seam where Google will eventually be plugged in.

Nothing in this file talks to Google today, and it does not pretend to. It
defines what the rest of the app is allowed to ask for, and fails loudly and
specifically if asked to do it before credentials exist.

To connect Google later:
  1. pip install google-api-python-client google-auth
  2. Point GOOGLE_SERVICE_ACCOUNT_FILE at the service-account JSON
  3. Implement fetch_daily_counts() below using the Sheets API
Nothing outside this file needs to change.
"""

from django.conf import settings


class IntegrationNotConfigured(RuntimeError):
    """Raised when a Google call is attempted without credentials."""


def is_configured():
    """Cheap check the whole app uses before offering any Google feature."""
    return bool(settings.GOOGLE_SERVICE_ACCOUNT_FILE)


class GoogleSheetsClient:
    """
    Reads response counts out of a Google Sheet.

    Deliberately unimplemented. A stub that returned fake numbers would be
    worse than no stub at all - it would make a broken integration look like a
    working one.
    """

    def __init__(self, credentials_path=None):
        self.credentials_path = credentials_path or settings.GOOGLE_SERVICE_ACCOUNT_FILE
        if not self.credentials_path:
            raise IntegrationNotConfigured(
                "GOOGLE_SERVICE_ACCOUNT_FILE is not set. "
                "Google Forms statistics can still be entered manually."
            )

    def fetch_daily_counts(self, sheet_id, since=None):
        """
        Should return [{'date': date, 'submission_count': int}, ...].

        Not implemented - the real Sheets call goes here.
        """
        raise NotImplementedError(
            "Implement fetch_daily_counts() with the Google Sheets API once "
            "service-account credentials are available."
        )
