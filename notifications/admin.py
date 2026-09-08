from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["recipient", "kind", "title", "created_at", "read_at", "emailed"]
    list_filter = ["kind", "created_at", "emailed"]
    search_fields = ["title", "body", "recipient__full_name", "recipient__email"]
    date_hierarchy = "created_at"
