from django.contrib import admin

from .models import ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "actor", "verb", "subject", "target_repr"]
    list_filter = ["verb", "created_at"]
    search_fields = ["target_repr", "actor__full_name", "subject__full_name"]
    date_hierarchy = "created_at"

    # The audit log is append-only. Django admin must not be a way around that.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
