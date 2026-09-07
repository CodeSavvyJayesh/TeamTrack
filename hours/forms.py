"""
Work-hour forms.

There is exactly one form here and only an administrator ever sees it. Note
what it does NOT contain: `duration_minutes`. The duration is computed in
WorkSession.save() from the two times, so no request can set it directly.
"""

from django import forms

from accounts.models import User

from .models import WorkSession

TEXT = {"class": "form-control"}
SELECT = {"class": "form-select"}


class WorkSessionForm(forms.ModelForm):
    class Meta:
        model = WorkSession
        fields = ["member", "date", "start_time", "end_time", "note"]
        widgets = {
            "member": forms.Select(attrs=SELECT),
            "date": forms.DateInput(attrs={**TEXT, "type": "date"}),
            "start_time": forms.TimeInput(attrs={**TEXT, "type": "time"}),
            "end_time": forms.TimeInput(attrs={**TEXT, "type": "time"}),
            "note": forms.TextInput(attrs={**TEXT, "placeholder": "Optional"}),
        }
        help_texts = {
            "start_time": "24-hour clock. The total is calculated for you.",
            "end_time": "Must be later than the start time on the same date.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assignable = User.objects.filter(is_active=True)
        if self.instance.pk and self.instance.member_id:
            assignable = assignable | User.objects.filter(pk=self.instance.member_id)
        self.fields["member"].queryset = assignable.distinct()

    # There is deliberately no clean() override here.
    #
    # WorkSession.clean() already carries the ordering and overlap rules, and
    # ModelForm runs it against the real instance during validation. Re-running
    # it here on a throwaway copy validated the wrong object: the copy always
    # looks like a new row, so editing an existing record failed its own
    # uniqueness check. Keeping the rules on the model means they apply
    # identically through this form, the Django admin, and any script.


class WorkSessionFilterForm(forms.Form):
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
