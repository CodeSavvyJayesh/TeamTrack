"""
Read-side helpers for work hours.

Kept out of the views so the member dashboard, the admin dashboard and the
member detail page all compute "hours this week" exactly the same way.
"""

from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from .models import WorkSession


def week_bounds(day=None):
    """Monday..Sunday containing `day`."""
    day = day or timezone.localdate()
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def month_bounds(day=None):
    day = day or timezone.localdate()
    start = day.replace(day=1)
    next_month = (start + timedelta(days=32)).replace(day=1)
    return start, next_month - timedelta(days=1)


def totals_for(member, day=None):
    """{'today': m, 'week': m, 'month': m} in minutes for one member."""
    day = day or timezone.localdate()
    week_start, week_end = week_bounds(day)
    month_start, month_end = month_bounds(day)
    sessions = WorkSession.objects.filter(member=member)
    return {
        "today": sessions.on(day).total_minutes(),
        "week": sessions.between(week_start, week_end).total_minutes(),
        "month": sessions.between(month_start, month_end).total_minutes(),
    }


def team_totals(day=None):
    """Same three numbers, summed across everyone."""
    day = day or timezone.localdate()
    week_start, week_end = week_bounds(day)
    month_start, month_end = month_bounds(day)
    sessions = WorkSession.objects.all()
    return {
        "today": sessions.on(day).total_minutes(),
        "week": sessions.between(week_start, week_end).total_minutes(),
        "month": sessions.between(month_start, month_end).total_minutes(),
    }


def daily_series(member=None, days=7, end=None):
    """
    Minutes per day for the last `days` days, oldest first.

    Returns ({labels}, {values}) ready for Chart.js. Days with no sessions come
    back as 0 rather than being missing, so the chart has no gaps.
    """
    end = end or timezone.localdate()
    start = end - timedelta(days=days - 1)

    queryset = WorkSession.objects.between(start, end)
    if member is not None:
        queryset = queryset.filter(member=member)

    by_day = {
        row["date"]: row["total"]
        for row in queryset.values("date").annotate(total=Sum("duration_minutes"))
    }

    labels, values = [], []
    for offset in range(days):
        current = start + timedelta(days=offset)
        labels.append(current.strftime("%a %d"))
        values.append(round((by_day.get(current) or 0) / 60, 2))
    return labels, values
