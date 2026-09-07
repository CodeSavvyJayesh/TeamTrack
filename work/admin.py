from django.contrib import admin

from .models import Project, Task


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "created_by", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name"]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ["title", "assigned_to", "project", "status", "priority", "due_date"]
    list_filter = ["status", "priority", "project"]
    search_fields = ["title", "description"]
    autocomplete_fields = ["assigned_to", "created_by"]
    date_hierarchy = "created_at"
