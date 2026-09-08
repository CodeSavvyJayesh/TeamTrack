"""
Puts the unread count and the latest few notifications into every template,
so the bell in the topbar works on every page without each view remembering
to provide them.
"""

from .models import Notification


def notifications(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}

    recent = list(
        Notification.objects.for_user(user).select_related("recipient")[:6]
    )
    return {
        "notification_unread_count": Notification.objects.for_user(user).unread().count(),
        "notification_recent": recent,
    }
