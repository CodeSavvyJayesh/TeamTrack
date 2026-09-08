"""
Starting, stopping and repairing attendance sessions.

All the rules live here so the login signal, the logout signal, the management
command and any future manual button all behave identically.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import AttendanceSession

logger = logging.getLogger(__name__)


def max_session_duration():
    return timedelta(hours=settings.ATTENDANCE_MAX_HOURS)


def open_session_for(member):
    """The member's currently running session, or None."""
    return AttendanceSession.objects.filter(member=member, ended_at__isnull=True).first()


def start_session(member, source=AttendanceSession.StartSource.LOGIN, when=None):
    """
    Begin tracking. Safe to call on every login.

    If a session is already running it is returned untouched, so signing in on
    a phone while already signed in on a laptop does not create a second one
    and double-count the day.

    If the running session is older than the cap, it is closed first - the
    person clearly went home without signing out, and their new sign-in is the
    start of a new day, not a continuation.
    """
    existing = open_session_for(member)
    if existing is not None:
        age = timezone.now() - existing.started_at
        if age <= max_session_duration():
            return existing
        close_stale(existing)

    return AttendanceSession.objects.create(
        member=member, started_at=when or timezone.now(), start_source=source
    )


def end_session(member, source=AttendanceSession.EndSource.LOGOUT, when=None):
    """Stop tracking. Returns the closed session, or None if none was running."""
    session = open_session_for(member)
    if session is None:
        return None

    now = when or timezone.now()
    # Someone who left it open for days should not get a 40-hour record just
    # because they eventually clicked Sign out.
    if now - session.started_at > max_session_duration():
        return close_stale(session)

    return session.close(when=now, source=source)


def close_stale(session):
    """
    Close a forgotten session at the cap and flag it.

    The flag matters more than the number. An auto-closed session is not a
    measurement of anything - it means nobody signed out - and the UI says so
    rather than quietly presenting it as a day's work.
    """
    capped_end = session.started_at + max_session_duration()
    logger.info("Auto-closing stale attendance session %s for %s", session.pk, session.member)
    return session.close(
        when=capped_end, source=AttendanceSession.EndSource.AUTO, auto=True
    )


def close_all_stale():
    """Sweep every forgotten session. Returns how many were closed."""
    cutoff = timezone.now() - max_session_duration()
    stale = AttendanceSession.objects.filter(ended_at__isnull=True, started_at__lt=cutoff)
    count = 0
    for session in stale.select_related("member"):
        close_stale(session)
        count += 1
    return count
