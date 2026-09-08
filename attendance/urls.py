from django.urls import path

from . import views

app_name = "attendance"

urlpatterns = [
    path("", views.AttendanceListView.as_view(), name="list"),
    path("stop/", views.StopSessionView.as_view(), name="stop"),
]
