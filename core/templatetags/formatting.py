"""
Display helpers.

`duration_format` is the single place that turns stored minutes into "6h 30m".
Every template showing work hours uses it, so the member view and the admin
view can never disagree about how the same number reads.
"""

from django import template

register = template.Library()


@register.filter
def duration_format(minutes):
    """390 -> '6h 30m'.  60 -> '1h'.  45 -> '45m'.  0 or None -> '0h'."""
    if minutes in (None, ""):
        return "0h"
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return "0h"
    if minutes <= 0:
        return "0h"
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f"{hours}h {remainder}m"
    return f"{hours}h" if hours else f"{remainder}m"


@register.filter
def dict_get(mapping, key):
    """
    Look up a dictionary by a variable key, which Django templates can't do.

    Used for the "today's hours per member" map, which is built in one query
    rather than one per table row.
    """
    if not hasattr(mapping, "get"):
        return None
    return mapping.get(key)
