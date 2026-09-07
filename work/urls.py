from django.urls import path

from . import views

app_name = "work"

urlpatterns = [
    path("", views.TaskListView.as_view(), name="task_list"),
    path("new/", views.TaskCreateView.as_view(), name="task_create"),
    path("<int:pk>/", views.TaskDetailView.as_view(), name="task_detail"),
    path("<int:pk>/edit/", views.TaskUpdateView.as_view(), name="task_edit"),
    path("<int:pk>/status/", views.TaskStatusUpdateView.as_view(), name="task_status"),
    path("projects/", views.ProjectListView.as_view(), name="project_list"),
    path("projects/new/", views.ProjectCreateView.as_view(), name="project_create"),
    path("projects/<int:pk>/edit/", views.ProjectUpdateView.as_view(), name="project_edit"),
]
