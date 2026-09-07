"""
Root URL configuration.

Each app owns its own urls.py with an app_name namespace, so every link in a
template is a {% url 'app:name' %} and no path is written twice.
"""

from django.conf import settings  # noqa: F401
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Django's own admin stays available as a secondary maintenance tool.
    # The real administrator experience is the custom dashboard.
    path("django-admin/", admin.site.urls),

    path("", include("dashboard.urls")),
    path("accounts/", include("accounts.urls")),
    path("members/", include("members.urls")),
    path("tasks/", include("work.urls")),
    path("hours/", include("hours.urls")),
    path("files/", include("storage.urls")),
    path("reports/", include("reports.urls")),
    path("forms/", include("integrations.google.urls")),
    path("setup/", include("core.urls")),
]

# MEDIA_URL is deliberately NOT routed, in development or production.
#
# storage.views.FileDownloadView is the only way to read an uploaded file, and
# it checks permission first. Adding static(MEDIA_URL, ...) here "just for
# development" would quietly open a second door with no check on it, and dev is
# exactly where you would stop noticing.

handler403 = "core.views.permission_denied"
handler404 = "core.views.page_not_found"
handler500 = "core.views.server_error"
