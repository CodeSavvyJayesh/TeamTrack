"""
How the application gets an Ether client.

Callers do:

    from integrations.ether.config import get_ether_client
    get_ether_client().send_event("task.completed", {"task_id": task.pk})

and never import a concrete class. Today that always resolves to
NullEtherClient. When a real client exists, this function is the only place
that changes.
"""

from django.conf import settings

from .null import NullEtherClient


def get_ether_client():
    if not settings.ETHER_BASE_URL:
        return NullEtherClient()

    # A real client is not implemented, because the Ether API specification is
    # not available. Configuring ETHER_BASE_URL without one must not silently
    # look like it worked - so we still return the null client and say so.
    import logging

    logging.getLogger(__name__).warning(
        "ETHER_BASE_URL is set but no Ether client is implemented yet. "
        "Using the null client. See integrations/ether/README.md."
    )
    return NullEtherClient()


def notify_ether(event_type, payload):
    """Convenience wrapper. Never raises - Ether must not break TeamTrack."""
    try:
        return get_ether_client().send_event(event_type, payload)
    except Exception:  # pragma: no cover
        return False
