"""Local development settings. Used by default via manage.py."""

from decouple import Csv, config

from .base import *  # noqa: F401,F403

DEBUG = True

# Always allow this machine. Anything extra (your wifi IP, so phones and other
# laptops on the same network can reach the app) comes from ALLOWED_HOSTS
# in .env as a comma-separated list.
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"] + config(
    "ALLOWED_HOSTS", default="", cast=Csv()  # noqa: F405
)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}


# --- Email ------------------------------------------------------------------
#
# Two modes, chosen by whether EMAIL_HOST is set in .env:
#
#   EMAIL_HOST blank (default)
#       Emails print into the terminal running `runserver`. The whole invite
#       flow works with no mail server and no credentials, and you cannot
#       accidentally email a real person while testing.
#
#   EMAIL_HOST set
#       Real SMTP. Invitations actually arrive in the recipient's inbox.
#
# Nothing else changes between the two - the same code sends the same email.

EMAIL_HOST = config("EMAIL_HOST", default="")

if EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
    EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
    EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
    EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
    DEFAULT_FROM_EMAIL = config(
        "DEFAULT_FROM_EMAIL", default=f"TeamTrack <{EMAIL_HOST_USER}>"
    )
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    DEFAULT_FROM_EMAIL = "TeamTrack <noreply@localhost>"
