"""
Google Forms screens.

These work today with hand-entered numbers. When the Google sync is
implemented, the same pages show the same rows - they just stop needing manual
entry. Nothing here assumes Google is connected.
"""

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from accounts.models import User
from core.mixins import AdminRequiredMixin, PageTitleMixin
from core.models import ActivityLog
from core.services import log_activity

from .client import is_configured
from .models import FormSubmissionStat, TrackedForm

TEXT = {"class": "form-control"}
SELECT = {"class": "form-select"}


class TrackedFormForm(forms.ModelForm):
    class Meta:
        model = TrackedForm
        fields = ["member", "name", "google_form_id", "sheet_id", "is_active"]
        widgets = {
            "member": forms.Select(attrs=SELECT),
            "name": forms.TextInput(attrs=TEXT),
            "google_form_id": forms.TextInput(attrs={**TEXT, "placeholder": "Leave blank for now"}),
            "sheet_id": forms.TextInput(attrs={**TEXT, "placeholder": "Leave blank for now"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only people whose profile says they do forms work.
        self.fields["member"].queryset = User.objects.filter(
            is_active=True, profile__tracks_google_forms=True
        )
        self.fields["member"].help_text = (
            "Only members with 'Tracks Google Forms' ticked on their profile appear here."
        )


class FormSubmissionStatForm(forms.ModelForm):
    class Meta:
        model = FormSubmissionStat
        fields = ["form", "date", "submission_count", "verified_count"]
        widgets = {
            "form": forms.Select(attrs=SELECT),
            "date": forms.DateInput(attrs={**TEXT, "type": "date"}),
            "submission_count": forms.NumberInput(attrs={**TEXT, "min": 0}),
            "verified_count": forms.NumberInput(attrs={**TEXT, "min": 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["form"].queryset = TrackedForm.objects.filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        submissions = cleaned.get("submission_count") or 0
        verified = cleaned.get("verified_count") or 0
        if verified > submissions:
            self.add_error("verified_count", "Cannot verify more submissions than were received.")
        return cleaned


class TrackedFormListView(LoginRequiredMixin, PageTitleMixin, ListView):
    template_name = "google/form_list.html"
    context_object_name = "forms_tracked"
    page_title = "Google Forms"

    def get_queryset(self):
        queryset = TrackedForm.objects.select_related("member")
        if not self.request.user.is_admin_user:
            queryset = queryset.filter(member=self.request.user)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["google_configured"] = is_configured()
        context["is_admin"] = self.request.user.is_admin_user
        context["recent_stats"] = (
            FormSubmissionStat.objects.for_user(self.request.user)
            .select_related("form", "form__member")[:25]
        )
        return context


class TrackedFormCreateView(AdminRequiredMixin, PageTitleMixin, CreateView):
    template_name = "google/form_form.html"
    form_class = TrackedFormForm
    success_url = reverse_lazy("google_forms:list")
    page_title = "Track a form"

    def form_valid(self, form):
        messages.success(self.request, "Form added.")
        return super().form_valid(form)


class TrackedFormUpdateView(AdminRequiredMixin, PageTitleMixin, UpdateView):
    template_name = "google/form_form.html"
    form_class = TrackedFormForm
    model = TrackedForm
    success_url = reverse_lazy("google_forms:list")
    page_title = "Edit tracked form"


class StatCreateView(AdminRequiredMixin, PageTitleMixin, CreateView):
    """Manual entry. The same rows a Google sync would write."""

    template_name = "google/stat_form.html"
    form_class = FormSubmissionStatForm
    success_url = reverse_lazy("google_forms:list")
    page_title = "Record submissions"

    def form_valid(self, form):
        response = super().form_valid(form)
        log_activity(
            actor=self.request.user,
            verb=ActivityLog.Verb.FORM_STATS_RECORDED,
            target=self.object,
            subject=self.object.form.member,
            target_repr=(
                f"{self.object.form.name}: {self.object.submission_count} submissions "
                f"on {self.object.date}"
            ),
        )
        messages.success(self.request, "Submission figures recorded.")
        return response
