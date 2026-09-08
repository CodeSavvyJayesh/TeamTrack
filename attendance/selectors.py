"""
Read-side helpers for attendance.

Mirrors hours/selectors.py on purpose, so "today / this week / this month"
means exactly the same window for tracked time as it does for recorded time.
That is what makes the two numbers comparable on the same screen.
"""

from django.utils import timezone

from hours.selectors import month_bounds, week_bounds

from .models import AttendanceSession


def totals_for(member, day=None):
    """Tracked minutes for one member: today, this week, this month."""
    day = day or timezone.localdate()
    week_start, week_end = week_bounds(day)
    month_start, month_end = month_bounds(day)
    sessions = AttendanceSession.objects.filter(member=member)
    return {
        "today": sessions.on_date(day).total_minutes(),
        "week": sessions.between(week_start, week_end).total_minutes(),
        "month": sessions.between(month_start, month_end).total_minutes(),
    }


def team_totals(day=None):
    day = day or timezone.localdate()
    week_start, week_end = week_bounds(day)
    sessions = AttendanceSession.objects.all()
    return {
        "today": sessions.on_date(day).total_minutes(),
        "week": sessions.between(week_start, week_end).total_minutes(),
    }


def tracked_minutes_by_member(day=None):
    """{member_id: minutes} for one day, in a single query."""
    from django.db.models import Sum

    day = day or timezone.localdate()
    return {
        row["member_id"]: row["total"] or 0
        for row in AttendanceSession.objects.on_date(day)
        .values("member_id")
        .annotate(total=Sum("duration_minutes"))
    }


def currently_signed_in():
    """Everyone with a session running right now."""
    return (
        AttendanceSession.objects.open()
        .select_related("member")
        .order_by("started_at")
    )
