from django.urls import path

from . import views

app_name = "hours"

urlpatterns = [
    path("", views.WorkSessionListView.as_view(), name="list"),
    # Every URL below is administrator-only.
    path("new/", views.WorkSessionCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", views.WorkSessionUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.WorkSessionDeleteView.as_view(), name="delete"),
]
