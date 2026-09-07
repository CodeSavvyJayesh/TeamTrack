from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.SetupCheckView.as_view(), name="setup_check"),
]
