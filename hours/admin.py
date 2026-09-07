from django.contrib import admin

from .models import WorkSession


@admin.register(WorkSession)
class WorkSessionAdmin(admin.ModelAdmin):
    list_display = ["member", "date", "start_time", "end_time", "duration_display", "entered_by"]
    list_filter = ["date", "member"]
    search_fields = ["member__full_name", "note"]
    date_hierarchy = "date"
    # duration_minutes is computed in save(); it must never be typed in.
    readonly_fields = ["duration_minutes"]
