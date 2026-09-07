"""
The Ether integration contract.

Ether is a separate platform. Its API specification does not exist here, so
this module invents nothing: no endpoints, no URLs, no payload schemas, no
authentication scheme. What it defines is the set of things TeamTrack would
want to say to Ether, expressed as method names, so the calling code can be
written and tested today against a client that does nothing.

When the real specification arrives, subclass EtherClient, implement these
methods, and point ETHER_BASE_URL at it. No caller changes.
"""

from abc import ABC, abstractmethod


class EtherClient(ABC):
    """What TeamTrack needs from Ether. Nothing about how Ether provides it."""

    @abstractmethod
    def send_event(self, event_type, payload):
        """
        Notify Ether that something happened in TeamTrack.

        event_type - a short string, e.g. "task.completed", "member.activated"
        payload    - a plain JSON-serialisable dict

        Returns True if Ether accepted it.
        """

    @abstractmethod
    def fetch_status(self):
        """Return a dict describing whether Ether is reachable and healthy."""

    @property
    def is_live(self):
        """False for any client that does not actually reach Ether."""
        return False
