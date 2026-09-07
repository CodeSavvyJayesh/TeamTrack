from django import forms

from accounts.models import User
from work.models import Task

from .models import DailyReport

TEXT = {"class": "form-control"}
SELECT = {"class": "form-select"}


class DailyReportForm(forms.ModelForm):
    """
    `member` is not a field. It is set from request.user in the view, so a
    member cannot file a report in someone else's name.
    """

    class Meta:
        model = DailyReport
        fields = ["date", "summary", "work_completed", "blockers", "notes", "related_tasks"]
        widgets = {
            "date": forms.DateInput(attrs={**TEXT, "type": "date"}),
            "summary": forms.TextInput(attrs={**TEXT, "placeholder": "One line about today"}),
            "work_completed": forms.Textarea(attrs={**TEXT, "rows": 5}),
            "blockers": forms.Textarea(attrs={**TEXT, "rows": 3}),
            "notes": forms.Textarea(attrs={**TEXT, "rows": 3}),
            "related_tasks": forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
        }

    def __init__(self, *args, member=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.member = member
        # Only tasks this person can see are offered.
        self.fields["related_tasks"].queryset = (
            Task.objects.for_user(member) if member else Task.objects.none()
        )
        self.fields["related_tasks"].required = False

    def clean_date(self):
        date = self.cleaned_data["date"]
        if self.member is None:
            return date
        existing = DailyReport.objects.filter(member=self.member, date=date)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError(
                "You already filed a report for that date. Edit the existing one instead."
            )
        return date


class ReportFilterForm(forms.Form):
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
