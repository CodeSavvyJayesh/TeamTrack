"""
The clock, wired to signing in and signing out.

Django fires user_logged_in and user_logged_out for us, so this works no matter
how the person authenticated - the login page, a password reset, or anything
added later. There is no JavaScript involved and no timer running in the
browser, so closing the laptop cannot fake extra time.
"""

import logging

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from .models import AttendanceSession
from .services import end_session, start_session

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def begin_attendance(sender, request, user, **kwargs):
    try:
        start_session(user, source=AttendanceSession.StartSource.LOGIN)
    except Exception:  # pragma: no cover - never block a login over this
        logger.exception("Could not start attendance session for %s", user)


@receiver(user_logged_out)
def finish_attendance(sender, request, user, **kwargs):
    # user is None when an anonymous session is flushed.
    if user is None:
        return
    try:
        end_session(user, source=AttendanceSession.EndSource.LOGOUT)
    except Exception:  # pragma: no cover - never block a logout over this
        logger.exception("Could not close attendance session for %s", user)
