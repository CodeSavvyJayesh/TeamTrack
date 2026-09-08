from django.contrib import admin

from .models import AttendanceSession


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ["member", "started_at", "ended_at", "duration_display",
                    "start_source", "end_source", "auto_closed"]
    list_filter = ["auto_closed", "start_source", "end_source", "started_at"]
    search_fields = ["member__full_name", "member__email"]
    date_hierarchy = "started_at"
    readonly_fields = ["duration_minutes"]

    # Attendance is a machine record. Corrections belong on the WorkSession,
    # where they are attributed to whoever made them.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
