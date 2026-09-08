"""
Create the administrator account on first deploy, from environment variables.

`createsuperuser` cannot run in a build script - it is interactive, and piping
a password into it puts that password in the deploy log. This reads from the
environment instead, does nothing if the account already exists, and never
prints or changes an existing password.

    ADMIN_EMAIL=hetansh@example.com
    ADMIN_PASSWORD=<a long random string>
    ADMIN_NAME="Hetansh Doshi"

Once the account exists, remove ADMIN_PASSWORD from the environment. The
command is safe to leave in the build - it becomes a no-op.
"""

from decouple import config
from django.core.management.base import BaseCommand

from accounts.models import User


class Command(BaseCommand):
    help = "Create the administrator account from environment variables, if absent."

    def handle(self, *args, **options):
        email = config("ADMIN_EMAIL", default="").strip().lower()
        password = config("ADMIN_PASSWORD", default="")
        full_name = config("ADMIN_NAME", default="Administrator")

        if not email or not password:
            self.stdout.write(
                "ADMIN_EMAIL / ADMIN_PASSWORD not set - skipping administrator bootstrap."
            )
            return

        if User.objects.filter(email=email).exists():
            self.stdout.write(f"Administrator {email} already exists - nothing to do.")
            return

        if len(password) < 12:
            self.stderr.write(
                "ADMIN_PASSWORD is shorter than 12 characters. Refusing to create "
                "an administrator with a weak password."
            )
            return

        User.objects.create_superuser(email=email, password=password, full_name=full_name)
        self.stdout.write(self.style.SUCCESS(f"Created administrator {email}."))
        self.stdout.write(
            self.style.WARNING(
                "Now remove ADMIN_PASSWORD from the environment and change the "
                "password after first sign-in."
            )
        )
