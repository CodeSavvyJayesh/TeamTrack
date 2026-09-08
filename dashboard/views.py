"""
Dashboards.

This app is read-only. It composes data from the other apps and writes nothing,
which is why it can safely know about all of them.

The router at "/" is what makes one URL work for two roles: an admin lands on
the team overview, a member on their own. There is no per-person branching
below that - both templates are driven entirely by the database.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Sum
from django.shortcuts import redirect
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from accounts.models import Invitation, User
from attendance.selectors import totals_for as tracked_totals_for
from attendance.models import AttendanceSession
from attendance.selectors import tracked_minutes_by_member
from core.mixins import AdminRequiredMixin, PageTitleMixin
from core.models import ActivityLog
from hours.models import WorkSession
from hours.selectors import daily_series, team_totals, totals_for, week_bounds
from integrations.google.models import FormSubmissionStat
from reports.models import DailyReport
from storage.models import UploadedFile
from work.models import Task


class DashboardRouterView(LoginRequiredMixin, View):
    """One entry point, two destinations, decided by role."""

    def get(self, request):
        if request.user.is_admin_user:
            return redirect("dashboard:admin")
        return redirect("dashboard:member")


class MemberDashboardView(LoginRequiredMixin, PageTitleMixin, TemplateView):
    template_name = "dashboard/member_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.localdate()

        context["page_title"] = f"{user.get_short_name()}'s dashboard"
        context["totals"] = totals_for(user)          # admin-entered, official
        context["tracked"] = tracked_totals_for(user)  # measured by the system

        tasks = Task.objects.filter(assigned_to=user)
        context["task_counts"] = {
            "completed": tasks.filter(status=Task.Status.COMPLETED).count(),
            "pending": tasks.filter(status=Task.Status.PENDING).count(),
            "in_progress": tasks.filter(status=Task.Status.IN_PROGRESS).count(),
            "blocked": tasks.filter(status=Task.Status.BLOCKED).count(),
            "overdue": tasks.overdue().count(),
        }
        context["open_tasks"] = tasks.open().select_related("project")[:8]
        context["recent_files"] = UploadedFile.objects.filter(uploaded_by=user)[:5]
        context["recent_activity"] = ActivityLog.objects.filter(subject=user).select_related("actor")[:8]
        context["todays_report"] = DailyReport.objects.filter(member=user, date=today).first()

        labels, values = daily_series(member=user, days=7)
        context["chart_labels"] = labels
        context["chart_values"] = values

        # Only members whose profile enables it see any Forms figures at all.
        # Everyone else gets no card, not an empty one showing zero.
        context["tracks_forms"] = user.profile.tracks_google_forms
        if context["tracks_forms"]:
            week_start, _ = week_bounds(today)
            stats = FormSubmissionStat.objects.filter(form__member=user)
            context["form_stats"] = {
                "today": stats.filter(date=today).total_submissions(),
                "week": stats.filter(date__gte=week_start).total_submissions(),
                "month": stats.filter(date__gte=today.replace(day=1)).total_submissions(),
            }
        return context


class AdminDashboardView(AdminRequiredMixin, PageTitleMixin, TemplateView):
    template_name = "dashboard/admin_dashboard.html"
    page_title = "Team overview"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()

        members = (
            User.objects.filter(role=User.Role.MEMBER)
            .select_related("profile")
            .annotate(
                open_tasks=Count("tasks", filter=~Q(tasks__status=Task.Status.COMPLETED), distinct=True),
                done_tasks=Count("tasks", filter=Q(tasks__status=Task.Status.COMPLETED), distinct=True),
            )
            .order_by("full_name")
        )

        # One query for everyone's minutes today, rather than one per row.
        today_minutes = {
            row["member_id"]: row["total"]
            for row in WorkSession.objects.filter(date=today)
            .values("member_id")
            .annotate(total=Sum("duration_minutes"))
        }

        # Recorded (what Hetansh entered) next to tracked (what the system saw).
        # Where the two disagree is the interesting column.
        tracked_minutes = tracked_minutes_by_member(today)
        open_now = set(
            AttendanceSession.objects.open().values_list("member_id", flat=True)
        )

        context["rows"] = [
            {
                "member": member,
                "today_minutes": today_minutes.get(member.pk, 0),
                "tracked_minutes": tracked_minutes.get(member.pk, 0),
                "signed_in": member.pk in open_now,
                "open_tasks": member.open_tasks,
                "done_tasks": member.done_tasks,
            }
            for member in members
        ]

        all_tasks = Task.objects.all()
        context["stats"] = {
            "members_total": members.count(),
            "members_active": members.filter(is_active=True).count(),
            "pending_invitations": Invitation.objects.pending().count(),
            "tasks_completed": all_tasks.completed().count(),
            "tasks_open": all_tasks.open().count(),
            "tasks_overdue": all_tasks.overdue().count(),
        }
        context["totals"] = team_totals(today)
        context["recent_uploads"] = UploadedFile.objects.select_related("uploaded_by")[:6]
        context["recent_reports"] = DailyReport.objects.select_related("member")[:6]
        context["recent_activity"] = ActivityLog.objects.select_related("actor", "subject")[:10]

        labels, values = daily_series(member=None, days=7)
        context["chart_labels"] = labels
        context["chart_values"] = values
        return context


class ActivityLogView(AdminRequiredMixin, PageTitleMixin, TemplateView):
    template_name = "core/activity_list.html"
    page_title = "Activity log"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entries = ActivityLog.objects.select_related("actor", "subject")

        verb = self.request.GET.get("verb")
        if verb:
            entries = entries.filter(verb=verb)

        context["entries"] = entries[:200]
        context["verbs"] = ActivityLog.Verb.choices
        context["selected_verb"] = verb or ""
        return context
