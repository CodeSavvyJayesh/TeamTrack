from django.contrib import admin

from .models import FormSubmissionStat, TrackedForm


@admin.register(TrackedForm)
class TrackedFormAdmin(admin.ModelAdmin):
    list_display = ["name", "member", "is_connected", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "member__full_name"]


@admin.register(FormSubmissionStat)
class FormSubmissionStatAdmin(admin.ModelAdmin):
    list_display = ["form", "date", "submission_count", "verified_count", "source"]
    list_filter = ["date", "form"]
    date_hierarchy = "date"
