"""
Work hours.

The rule from the brief - "members do not enter their own working hours" - is
enforced here in two independent ways on every write view:

  AdminRequiredMixin   blocks the request before the view body runs
  AdminOnlyWriteMixin  rejects any non-safe HTTP method for a non-admin

Two guards for one rule is deliberate. This is the permission most likely to be
accidentally weakened by a later refactor.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.mixins import AdminOnlyWriteMixin, AdminRequiredMixin, PageTitleMixin
from core.models import ActivityLog
from core.services import log_activity
from integrations.ether.config import notify_ether

from .forms import WorkSessionFilterForm, WorkSessionForm
from .models import WorkSession
from .selectors import team_totals, totals_for


class WorkSessionListView(LoginRequiredMixin, PageTitleMixin, ListView):
    """Read-only for members, and the management screen for administrators."""

    template_name = "hours/worksession_list.html"
    context_object_name = "sessions"
    paginate_by = 30
    page_title = "Working hours"

    def get_queryset(self):
        # Cached: get_context_data needs the same filtered queryset for its
        # total, and rebuilding it would re-validate the filter form and re-run
        # the query on every page load.
        if hasattr(self, "_filtered_queryset"):
            return self._filtered_queryset

        user = self.request.user
        queryset = WorkSession.objects.for_user(user).select_related(
            "member", "entered_by", "updated_by"
        )

        self.filter_form = WorkSessionFilterForm(
            self.request.GET or None, show_member_filter=user.is_admin_user
        )
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data.get("member"):
                queryset = queryset.filter(member=data["member"])
            if data.get("date_from"):
                queryset = queryset.filter(date__gte=data["date_from"])
            if data.get("date_to"):
                queryset = queryset.filter(date__lte=data["date_to"])

        self._filtered_queryset = queryset
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["filter_form"] = self.filter_form
        context["totals"] = team_totals() if user.is_admin_user else totals_for(user)
        context["can_manage"] = user.is_admin_user
        # The total for whatever the filter currently shows.
        context["filtered_minutes"] = self.get_queryset().total_minutes()
        return context


class WorkSessionCreateView(AdminRequiredMixin, AdminOnlyWriteMixin, PageTitleMixin, CreateView):
    template_name = "hours/worksession_form.html"
    form_class = WorkSessionForm
    success_url = reverse_lazy("hours:list")
    page_title = "Add working hours"

    def form_valid(self, form):
        form.instance.entered_by = self.request.user
        response = super().form_valid(form)
        log_activity(
            actor=self.request.user,
            verb=ActivityLog.Verb.HOURS_ADDED,
            target=self.object,
            subject=self.object.member,
            target_repr=(
                f"{self.object.member.full_name}: {self.object.date} "
                f"{self.object.start_time:%H:%M}-{self.object.end_time:%H:%M} "
                f"({self.object.duration_display})"
            ),
        )
        notify_ether("hours.recorded", {"session_id": self.object.pk,
                                        "member_id": self.object.member_id})
        messages.success(
            self.request,
            f"Recorded {self.object.duration_display} for {self.object.member.full_name}.",
        )
        return response


class WorkSessionUpdateView(AdminRequiredMixin, AdminOnlyWriteMixin, PageTitleMixin, UpdateView):
    template_name = "hours/worksession_form.html"
    form_class = WorkSessionForm
    model = WorkSession
    success_url = reverse_lazy("hours:list")
    page_title = "Edit working hours"

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        log_activity(
            actor=self.request.user,
            verb=ActivityLog.Verb.HOURS_UPDATED,
            target=self.object,
            subject=self.object.member,
            target_repr=(
                f"Corrected {self.object.member.full_name}'s hours on {self.object.date} "
                f"to {self.object.duration_display}"
            ),
        )
        messages.success(self.request, "Working hours updated.")
        return response


class WorkSessionDeleteView(AdminRequiredMixin, AdminOnlyWriteMixin, PageTitleMixin, DeleteView):
    template_name = "hours/worksession_confirm_delete.html"
    model = WorkSession
    success_url = reverse_lazy("hours:list")
    page_title = "Delete working hours"

    def form_valid(self, form):
        session = self.get_object()
        log_activity(
            actor=self.request.user,
            verb=ActivityLog.Verb.HOURS_DELETED,
            subject=session.member,
            target_repr=(
                f"Deleted {session.member.full_name}'s {session.duration_display} "
                f"on {session.date}"
            ),
        )
        messages.success(self.request, "Working-hour record deleted.")
        return super().form_valid(form)
