"""
One running attendance session per person, enforced by the database.

The constraint cannot be added while duplicates already exist, and a database
that has been running for a while may well have some - a signal that fired
twice, or two devices signing in at the same instant. So older duplicates are
closed first, keeping the most recent, which is the session the person is
actually in right now.
"""

from django.conf import settings
from django.db import migrations, models


def close_duplicate_open_sessions(apps, schema_editor):
    AttendanceSession = apps.get_model("attendance", "AttendanceSession")

    open_sessions = AttendanceSession.objects.filter(ended_at__isnull=True).order_by(
        "member_id", "-started_at"
    )

    seen_members = set()
    for session in open_sessions:
        if session.member_id not in seen_members:
            seen_members.add(session.member_id)  # keep the newest
            continue

        # An older duplicate. Close it at its own start time: it represents no
        # measured work, so it must not add minutes to anybody's total.
        session.ended_at = session.started_at
        session.duration_minutes = 0
        session.end_source = "AUTO"
        session.auto_closed = True
        session.save(
            update_fields=["ended_at", "duration_minutes", "end_source", "auto_closed"]
        )


def noop(apps, schema_editor):
    """Reversing only drops the constraint; there is nothing to undo in the data."""


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(close_duplicate_open_sessions, noop),
        migrations.AddConstraint(
            model_name="attendancesession",
            constraint=models.UniqueConstraint(
                condition=models.Q(("ended_at__isnull", True)),
                fields=("member",),
                name="one_open_attendance_session_per_member",
            ),
        ),
    ]
