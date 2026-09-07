"""
The default Ether client: does nothing, successfully.

Every integration point in the application calls this today. It makes no
network request and returns nothing that could be mistaken for real data. Its
only side effect is a debug log line, so you can see which events *would* be
sent once Ether is connected.
"""

import logging

from .base import EtherClient

logger = logging.getLogger(__name__)


class NullEtherClient(EtherClient):
    def send_event(self, event_type, payload):
        logger.debug("Ether not configured; dropping event %s: %s", event_type, payload)
        return False

    def fetch_status(self):
        return {"configured": False, "detail": "Ether integration is not configured."}

    @property
    def is_live(self):
        return False
