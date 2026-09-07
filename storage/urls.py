from django.urls import path

from . import views

app_name = "storage"

urlpatterns = [
    path("", views.FileListView.as_view(), name="list"),
    path("upload/", views.FileUploadView.as_view(), name="upload"),
    path("<int:pk>/download/", views.FileDownloadView.as_view(), name="download"),
    path("<int:pk>/delete/", views.FileDeleteView.as_view(), name="delete"),
]
