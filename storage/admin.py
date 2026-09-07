from django.contrib import admin

from .models import UploadedFile


@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ["original_name", "uploaded_by", "size_display", "visibility", "created_at"]
    list_filter = ["visibility", "created_at"]
    search_fields = ["original_name", "description"]
    readonly_fields = ["original_name", "content_type", "size_bytes"]
