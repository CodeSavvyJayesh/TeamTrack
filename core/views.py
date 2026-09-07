"""
Core views: the setup page and the three error handlers.

The error pages matter more than they look. A member who guesses an admin URL
must get a page that says "you don't have access" without leaking a stack
trace or the shape of the data behind it.
"""

import django
from django.conf import settings
from django.db import connection
from django.shortcuts import render
from django.views.generic import TemplateView

from .mixins import AdminRequiredMixin, PageTitleMixin


class SetupCheckView(AdminRequiredMixin, PageTitleMixin, TemplateView):
    """
    A one-screen sanity check that the environment is wired up correctly.

    Administrator-only. It reports the Django version, the settings module,
    DEBUG state and which integrations are configured - useful to you, and a
    free fingerprint of the stack for anyone else. So it is not public.
    """

    template_name = "core/home.html"
    page_title = "Environment check"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["checks"] = [
            ("Django version", django.get_version()),
            ("Settings module", settings.SETTINGS_MODULE),
            ("Debug mode", "On" if settings.DEBUG else "Off"),
            ("Database engine", connection.vendor),
            ("Time zone", settings.TIME_ZONE),
            ("Secret key loaded from .env", "Yes" if settings.SECRET_KEY else "No"),
            ("Max upload size", f"{settings.MAX_UPLOAD_SIZE_MB} MB"),
            ("Invitation validity", f"{settings.INVITATION_EXPIRY_DAYS} days"),
            ("Google integration", "Configured" if settings.GOOGLE_SERVICE_ACCOUNT_FILE else "Dormant"),
            ("Ether integration", "Configured" if settings.ETHER_BASE_URL else "Dormant"),
        ]
        return context


def permission_denied(request, exception=None):
    return render(request, "errors/403.html", status=403)


def page_not_found(request, exception=None):
    return render(request, "errors/404.html", status=404)


def server_error(request):
    return render(request, "errors/500.html", status=500)
