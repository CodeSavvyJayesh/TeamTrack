"""
Close attendance sessions nobody signed out of.

Run it nightly. Without this one command the whole feature rots: one forgotten
sign-out becomes a 40-hour "day" and every total downstream is wrong.

    python manage.py close_stale_attendance
    python manage.py close_stale_attendance --dry-run
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from attendance.models import AttendanceSession
from attendance.services import close_all_stale, max_session_duration


class Command(BaseCommand):
    help = "Close attendance sessions left open past the daily cap."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Show what would be closed, change nothing."
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - max_session_duration()
        stale = AttendanceSession.objects.filter(
            ended_at__isnull=True, started_at__lt=cutoff
        ).select_related("member")

        if not stale.exists():
            self.stdout.write(self.style.SUCCESS("Nothing to close."))
            return

        for session in stale:
            self.stdout.write(
                f"  {session.member}: open since "
                f"{timezone.localtime(session.started_at):%d %b %H:%M}"
            )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(f"Dry run - {stale.count()} would be closed."))
            return

        closed = close_all_stale()
        self.stdout.write(self.style.SUCCESS(f"Closed {closed} stale session(s)."))
