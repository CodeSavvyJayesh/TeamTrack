"""
Refresh Google Forms statistics.

Safe to schedule even when Google is not configured - it reports that the
integration is dormant and exits 0 rather than failing.

    python manage.py sync_google_forms
    python manage.py sync_google_forms --form 3
"""

from django.core.management.base import BaseCommand

from integrations.google.client import is_configured
from integrations.google.models import TrackedForm
from integrations.google.services import sync_form_stats


class Command(BaseCommand):
    help = "Pull submission counts for tracked Google Forms."

    def add_arguments(self, parser):
        parser.add_argument("--form", type=int, help="Sync only this TrackedForm id.")

    def handle(self, *args, **options):
        if not is_configured():
            self.stdout.write(self.style.WARNING(
                "Google integration is dormant (GOOGLE_SERVICE_ACCOUNT_FILE is not set). "
                "Statistics can still be entered manually."
            ))
            return

        forms = TrackedForm.objects.filter(is_active=True)
        if options.get("form"):
            forms = forms.filter(pk=options["form"])

        total = 0
        for form in forms:
            written = sync_form_stats(form)
            total += written
            self.stdout.write(f"  {form.name}: {written} row(s)")

        self.stdout.write(self.style.SUCCESS(f"Done. {total} row(s) written."))
