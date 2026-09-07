from django.urls import path

from . import views

app_name = "google_forms"

urlpatterns = [
    path("", views.TrackedFormListView.as_view(), name="list"),
    path("new/", views.TrackedFormCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", views.TrackedFormUpdateView.as_view(), name="edit"),
    path("stats/new/", views.StatCreateView.as_view(), name="stat_create"),
]
