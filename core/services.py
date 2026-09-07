"""
Small cross-app helpers that are not model methods and not views.

Keeping log_activity here means no app has to import another app's models just
to record that something happened.
"""

from .models import ActivityLog


def log_activity(actor, verb, target=None, subject=None, target_repr=""):
    """
    Record one consequential action.

    actor       - the User who did it (None for system/management commands)
    verb        - an ActivityLog.Verb value
    target      - the object acted on; its class name, pk and str() are stored
    subject     - the member the action concerns (defaults to target.member /
                  target.assigned_to / target itself when it is a User)
    target_repr - override the stored display string

    Never raises: an audit write must not be able to break the action it is
    describing.
    """
    try:
        target_model = ""
        target_id = None

        if target is not None:
            target_model = target.__class__.__name__
            target_id = getattr(target, "pk", None)
            if not target_repr:
                target_repr = str(target)[:255]

            if subject is None:
                subject = (
                    getattr(target, "member", None)
                    or getattr(target, "assigned_to", None)
                    or getattr(target, "uploaded_by", None)
                )
                # A User target is its own subject.
                if subject is None and target.__class__.__name__ == "User":
                    subject = target

        return ActivityLog.objects.create(
            actor=actor if getattr(actor, "pk", None) else None,
            subject=subject if getattr(subject, "pk", None) else None,
            verb=verb,
            target_repr=target_repr,
            target_model=target_model,
            target_id=target_id,
        )
    except Exception:  # pragma: no cover - audit logging is best effort
        return None
