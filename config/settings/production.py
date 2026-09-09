"""
Production settings.

Activate with:  DJANGO_SETTINGS_MODULE=config.settings.production

Everything secret comes from the environment and has NO fallback - the site
refuses to boot rather than start up quietly insecure. That is deliberate: a
default SECRET_KEY or a default database password is worse than a crash,
because a crash gets fixed and a silent default does not.
"""

import dj_database_url
from decouple import Csv, config

from .base import *  # noqa: F401,F403

DEBUG = False

# No fallback. If this is unset the site will not start.
SECRET_KEY = config("SECRET_KEY")

# Railway injects RAILWAY_PUBLIC_DOMAIN with the hostname it serves you on, and
# that name changes if the service is renamed. Reading it directly means the
# site works on the first deploy with nothing configured by hand - and getting
# this wrong is the single most common way a first Django deploy fails, with
# either DisallowedHost on every page or a CSRF error on every form.
RAILWAY_DOMAIN = config("RAILWAY_PUBLIC_DOMAIN", default="")

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="", cast=Csv())
if RAILWAY_DOMAIN and RAILWAY_DOMAIN not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RAILWAY_DOMAIN)
if not ALLOWED_HOSTS:
    raise RuntimeError(
        "Neither ALLOWED_HOSTS nor RAILWAY_PUBLIC_DOMAIN is set. Refusing to "
        "start rather than accept requests for any hostname."
    )

# Every host we answer on must also be allowed to POST to us over HTTPS.
CSRF_TRUSTED_ORIGINS = [
    origin if origin.startswith("http") else f"https://{origin}"
    for origin in config(
        "CSRF_TRUSTED_ORIGINS", default=",".join(ALLOWED_HOSTS), cast=Csv()
    )
]


# --- Database ---------------------------------------------------------------
# Render and most managed hosts inject a single DATABASE_URL. Falling back to
# the individual DB_* variables keeps a plain VPS working the same way.

DATABASE_URL = config("DATABASE_URL", default="")

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=config("DB_SSL_REQUIRE", default=True, cast=bool),
        )
    }
elif not config("DB_NAME", default=""):
    # Neither form of database configuration is present. Say so plainly:
    # letting decouple raise "DB_NAME not found" sends you looking for a
    # variable you were never supposed to set, when the real problem is a
    # missing DATABASE_URL.
    raise RuntimeError(
        "No database configured. On Railway, add a variable to the web "
        "service:  DATABASE_URL = ${{Postgres.DATABASE_URL}}  - adding the "
        "Postgres service to the project does not wire it up by itself. "
        "On a plain server, set DB_NAME / DB_USER / DB_PASSWORD instead."
    )
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("DB_NAME"),
            "USER": config("DB_USER"),
            "PASSWORD": config("DB_PASSWORD"),
            "HOST": config("DB_HOST", default="localhost"),
            "PORT": config("DB_PORT", default="5432"),
            "CONN_MAX_AGE": 600,
        }
    }


# --- Static and media -------------------------------------------------------
#
# Static files: WhiteNoise serves them from the app process with hashed names
# and long cache headers. No nginx or CDN needed at this size.
#
# Media files: on Render, Railway and most managed hosts the local disk is
# WIPED on every deploy. Uploaded files must live in object storage or they
# silently disappear the first time you push a change - which is the most
# common way a Django app loses real user data.
#
# Either way MEDIA_URL is never routed and the bucket stays PRIVATE.
# storage.views.FileDownloadView remains the only way to read an upload, and it
# checks permission before streaming a single byte.

MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405

USE_S3_MEDIA = bool(config("AWS_STORAGE_BUCKET_NAME", default=""))

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
    "default": (
        {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": config("AWS_STORAGE_BUCKET_NAME"),
                "access_key": config("AWS_ACCESS_KEY_ID"),
                "secret_key": config("AWS_SECRET_ACCESS_KEY"),
                "endpoint_url": config("AWS_S3_ENDPOINT_URL", default=None),
                "region_name": config("AWS_S3_REGION_NAME", default="auto"),
                # Private bucket. Nothing is readable by URL.
                "default_acl": None,
                "querystring_auth": True,
                "file_overwrite": False,
                "signature_version": "s3v4",
            },
        }
        if USE_S3_MEDIA
        else {"BACKEND": "django.core.files.storage.FileSystemStorage"}
    ),
}


# --- Email ------------------------------------------------------------------
#
# Railway, Render and Fly all block outbound SMTP ports (25, 465, 587) to keep
# their networks off spam blocklists. Django's SMTP backend fails there with
# "ConnectionRefusedError: [Errno 111] Connection refused" and no credentials
# can fix it, because nothing ever leaves the container.
#
# So: if BREVO_API_KEY is set, send over HTTPS on port 443 instead, which is
# never blocked. Otherwise fall back to SMTP for a plain VPS, where it works.

EMAIL_TIMEOUT = 10  # never let a slow mail server hang a web request
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

BREVO_API_KEY = config("BREVO_API_KEY", default="")

if BREVO_API_KEY:
    EMAIL_BACKEND = "core.email.BrevoAPIBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = config("EMAIL_HOST")
    EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
    EMAIL_HOST_USER = config("EMAIL_HOST_USER")
    EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD")
    EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)


# --- Security ---------------------------------------------------------------
# Assumes TLS terminates at the platform's proxy, which is how Render works.

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# Start HSTS short. Raise it once you are certain HTTPS works on every hostname
# you serve - a long max-age is very hard to walk back if you get it wrong.
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=3600, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False, cast=bool
)
SECURE_HSTS_PRELOAD = False

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Refuse a request body meaningfully larger than the biggest allowed upload.
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_BYTES + (1024 * 1024)  # noqa: F405


# --- Logging ----------------------------------------------------------------
#
# Without this, a 500 in production goes nowhere and you find out about bugs
# from whoever hit them. Everything goes to stdout, which Render, Railway,
# Docker and systemd all capture.

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        # Unhandled exceptions, with tracebacks.
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        # Our own apps, so notification and attendance warnings are visible.
        "accounts": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "attendance": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "notifications": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "storage": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "integrations": {"handlers": ["console"], "level": "INFO", "propagate": False},
        # Far too noisy at INFO; only complain about real problems.
        "django.db.backends": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
