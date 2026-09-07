from django.contrib import admin

from .models import DailyReport


@admin.register(DailyReport)
class DailyReportAdmin(admin.ModelAdmin):
    list_display = ["member", "date", "summary", "has_blockers"]
    list_filter = ["date", "member"]
    search_fields = ["summary", "work_completed", "blockers"]
    date_hierarchy = "date"
    filter_horizontal = ["related_tasks"]
