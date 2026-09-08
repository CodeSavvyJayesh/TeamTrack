"""
Attendance views.

Read-only for everyone. Members see their own sessions, administrators see the
whole team. Nobody edits a session here - it is a machine record, and the place
to correct a day is the admin-entered working hours.
"""

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views import View
from django.views.generic import ListView

from accounts.models import User
from core.mixins import PageTitleMixin
from hours.selectors import totals_for as recorded_totals_for

from .models import AttendanceSession
from .selectors import currently_signed_in, team_totals, totals_for

TEXT = {"class": "form-control"}
SELECT = {"class": "form-select"}


class AttendanceFilterForm(forms.Form):
    member = forms.ModelChoiceField(
        required=False, queryset=User.objects.all(), empty_label="All members",
        widget=forms.Select(attrs=SELECT),
    )
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={**TEXT, "type": "date"}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={**TEXT, "type": "date"}))

    def __init__(self, *args, **kwargs):
        show_member_filter = kwargs.pop("show_member_filter", True)
        super().__init__(*args, **kwargs)
        if not show_member_filter:
            del self.fields["member"]


class AttendanceListView(LoginRequiredMixin, PageTitleMixin, ListView):
    template_name = "attendance/attendance_list.html"
    context_object_name = "sessions"
    paginate_by = 30
    page_title = "Attendance"

    def get_queryset(self):
        if hasattr(self, "_queryset"):
            return self._queryset

        user = self.request.user
        queryset = AttendanceSession.objects.for_user(user).select_related("member")

        self.filter_form = AttendanceFilterForm(
            self.request.GET or None, show_member_filter=user.is_admin_user
        )
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data.get("member"):
                queryset = queryset.filter(member=data["member"])
            if data.get("date_from"):
                queryset = queryset.filter(started_at__date__gte=data["date_from"])
            if data.get("date_to"):
                queryset = queryset.filter(started_at__date__lte=data["date_to"])

        self._queryset = queryset
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["filter_form"] = self.filter_form
        context["is_admin"] = user.is_admin_user

        if user.is_admin_user:
            context["totals"] = team_totals()
            context["signed_in_now"] = currently_signed_in()
        else:
            context["totals"] = totals_for(user)
            # Side by side with what Hetansh actually recorded, so a member can
            # see the gap themselves rather than being surprised by it.
            context["recorded"] = recorded_totals_for(user)

        context["auto_closed_count"] = self.get_queryset().filter(auto_closed=True).count()
        return context


class StopSessionView(LoginRequiredMixin, View):
    """
    'I have finished for the day' without signing out.

    Signing out closes the session anyway, but people leave the tab open. This
    gives them a way to stop the clock honestly at the moment they stop working.
    """

    http_method_names = ["post"]

    def post(self, request):
        from .services import end_session

        session = end_session(request.user, source=AttendanceSession.EndSource.MANUAL)
        if session is None:
            messages.info(request, "You don't have a session running.")
        else:
            messages.success(
                request, f"Session stopped. Tracked {session.duration_display} today."
            )
        return redirect(request.POST.get("next") or "dashboard:home")
