from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.DashboardRouterView.as_view(), name="home"),
    path("my/", views.MemberDashboardView.as_view(), name="member"),
    path("team/", views.AdminDashboardView.as_view(), name="admin"),
    path("activity/", views.ActivityLogView.as_view(), name="activity"),
]
