"""
Settings shared by every environment.

Anything that differs between your laptop and a real server lives in
development.py or production.py instead. Nothing secret belongs in this file -
read it from the environment (.env) with decouple's `config()`.
"""

from pathlib import Path

from decouple import Csv, config
from django.contrib.messages import constants as message_constants

# config/settings/base.py -> config/settings -> config -> <project root>
BASE_DIR = Path(__file__).resolve().parent.parent.parent


# --- Security ---------------------------------------------------------------

SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="", cast=Csv())


# --- Applications -----------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

# Our own apps. Each phase adds one line here.
LOCAL_APPS = [
    "core",
    "accounts",
    "members",
    "work",
    "hours",
    "storage",
    "reports",
    "dashboard",
    "notifications",
    "attendance",
    "integrations.google",
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Project-wide templates live in /templates. App templates still work
        # via APP_DIRS, so both styles are available.
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.navigation",
                "notifications.context_processors.notifications",
                "attendance.context_processors.attendance",
            ],
        },
    },
]


# --- Passwords --------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- Internationalisation ---------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = config("TIME_ZONE", default="Asia/Kolkata")
USE_I18N = True
USE_TZ = True


# --- Static and media -------------------------------------------------------

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media is never served directly in production. Every download goes through a
# permission-checked view (see the storage app, Phase 6).
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Django tags error messages "error"; Bootstrap 5 has no .alert-error, only
# .alert-danger. Without this remap every error toast renders unstyled.
MESSAGE_TAGS = {message_constants.ERROR: "danger"}


# --- Authentication ---------------------------------------------------------
# Login is by email. There is no username field anywhere in this project.

AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "accounts:login"

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # the CSRF token must be readable by forms
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_AGE = 60 * 60 * 12  # 12 hours

# Uploads larger than this are streamed to a temp file instead of held in RAM.
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024


# --- Application rules ------------------------------------------------------
# Business rules that a future admin might want to tune without touching code.

INVITATION_EXPIRY_DAYS = config("INVITATION_EXPIRY_DAYS", default=7, cast=int)
MAX_UPLOAD_SIZE_MB = config("MAX_UPLOAD_SIZE_MB", default=10, cast=int)
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# --- Attendance -------------------------------------------------------------
# The clock starts when someone signs in and stops when they sign out. People
# forget to sign out, so any session still open past this many hours is closed
# automatically and flagged - see `manage.py close_stale_attendance`.
ATTENDANCE_MAX_HOURS = config("ATTENDANCE_MAX_HOURS", default=9, cast=int)


ALLOWED_UPLOAD_EXTENSIONS = [
    "pdf", "doc", "docx", "xls", "xlsx", "csv", "txt",
    "png", "jpg", "jpeg", "gif", "zip",
]


# --- Integrations -----------------------------------------------------------
# Both are dormant until configured. The application must run normally with
# these blank - that is a hard requirement, not a nicety.

GOOGLE_SERVICE_ACCOUNT_FILE = config("GOOGLE_SERVICE_ACCOUNT_FILE", default="")
ETHER_BASE_URL = config("ETHER_BASE_URL", default="")
ETHER_API_KEY = config("ETHER_API_KEY", default="")
