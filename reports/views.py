"""Daily reports: written by members, readable by their author and by admins."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from core.mixins import PageTitleMixin
from core.models import ActivityLog
from core.services import log_activity
from integrations.ether.config import notify_ether

from .forms import DailyReportForm, ReportFilterForm
from .models import DailyReport


class ReportListView(LoginRequiredMixin, PageTitleMixin, ListView):
    template_name = "reports/report_list.html"
    context_object_name = "reports"
    paginate_by = 20

    def get_queryset(self):
        user = self.request.user
        queryset = DailyReport.objects.for_user(user).select_related("member")
        self.filter_form = ReportFilterForm(
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
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "All reports" if self.request.user.is_admin_user else "My reports"
        context["filter_form"] = self.filter_form
        return context


class ReportDetailView(LoginRequiredMixin, PageTitleMixin, DetailView):
    template_name = "reports/report_detail.html"
    context_object_name = "report"

    def get_queryset(self):
        return DailyReport.objects.for_user(self.request.user).select_related("member")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Report - {self.object.date}"
        return context


class ReportCreateView(LoginRequiredMixin, PageTitleMixin, CreateView):
    template_name = "reports/report_form.html"
    form_class = DailyReportForm
    page_title = "New daily report"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["member"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.member = self.request.user
        response = super().form_valid(form)
        log_activity(
            actor=self.request.user,
            verb=ActivityLog.Verb.REPORT_SUBMITTED,
            target=self.object,
            subject=self.request.user,
            target_repr=f"Filed a report for {self.object.date}",
        )
        notify_ether("report.submitted", {"report_id": self.object.pk,
                                          "member_id": self.request.user.pk})
        messages.success(self.request, "Report saved.")
        return response


class ReportUpdateView(LoginRequiredMixin, PageTitleMixin, UpdateView):
    template_name = "reports/report_form.html"
    form_class = DailyReportForm
    page_title = "Edit daily report"

    def get_queryset(self):
        return DailyReport.objects.for_user(self.request.user)

    def get_object(self, queryset=None):
        report = super().get_object(queryset)
        # An admin can read every report but does not author them, so editing
        # someone else's words is not allowed.
        if report.member_id != self.request.user.pk:
            raise PermissionDenied("Only the author can edit a report.")
        return report

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["member"] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        log_activity(
            actor=self.request.user,
            verb=ActivityLog.Verb.REPORT_UPDATED,
            target=self.object,
            subject=self.request.user,
            target_repr=f"Updated their report for {self.object.date}",
        )
        messages.success(self.request, "Report updated.")
        return response
