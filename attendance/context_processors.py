"""
Puts the running session into every page, so the "Working since 10:04" pill in
the topbar appears everywhere without each view remembering to provide it.

One cheap indexed query per request for signed-in users, nothing for anyone else.
"""

from .services import open_session_for


def attendance(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {"attendance_open": open_session_for(user)}
