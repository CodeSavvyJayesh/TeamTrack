"""
The only function the rest of the application calls to refresh form data.

Everything above this layer reads FormSubmissionStat rows from the database and
never imports the client. That is what makes swapping "typed in by hand" for
"pulled from Google" a change to one file.
"""

import logging

from django.utils import timezone

from .client import GoogleSheetsClient, IntegrationNotConfigured, is_configured
from .models import FormSubmissionStat

logger = logging.getLogger(__name__)


def sync_form_stats(form, since=None):
    """
    Refresh one TrackedForm's statistics from Google.

    Returns the number of rows written. Returns 0 - without raising - when the
    integration is dormant, because "Google isn't set up" is a normal state for
    this application, not an error.
    """
    if not is_configured():
        logger.info("Google integration dormant; skipping sync for %s", form)
        return 0

    if not form.sheet_id:
        logger.info("%s has no sheet_id; skipping", form)
        return 0

    try:
        client = GoogleSheetsClient()
        rows = client.fetch_daily_counts(form.sheet_id, since=since)
    except (IntegrationNotConfigured, NotImplementedError) as exc:
        logger.warning("Google sync unavailable for %s: %s", form, exc)
        return 0

    written = 0
    for row in rows:
        FormSubmissionStat.objects.update_or_create(
            form=form,
            date=row["date"],
            defaults={
                "submission_count": row.get("submission_count", 0),
                "verified_count": row.get("verified_count", 0),
                "synced_at": timezone.now(),
            },
        )
        written += 1
    return written
