"""
Task forms.

There are two, and the split is the permission model:

  TaskForm       - administrators. Every field.
  TaskStatusForm - members. Status only.

A member's POST is validated against a form that has no `assigned_to` field, so
reassigning a task to themselves is not something they can express, let alone
have rejected.
"""

from django import forms

from accounts.models import User

from .models import Project, Task

TEXT = {"class": "form-control"}
SELECT = {"class": "form-select"}


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "description", "project", "assigned_to", "status", "priority", "due_date", "notes"]
        widgets = {
            "title": forms.TextInput(attrs=TEXT),
            "description": forms.Textarea(attrs={**TEXT, "rows": 4}),
            "project": forms.Select(attrs=SELECT),
            "assigned_to": forms.Select(attrs=SELECT),
            "status": forms.Select(attrs=SELECT),
            "priority": forms.Select(attrs=SELECT),
            "due_date": forms.DateInput(attrs={**TEXT, "type": "date"}),
            "notes": forms.Textarea(attrs={**TEXT, "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only active people can be given new work. Someone already assigned to
        # this task stays selectable so editing it doesn't silently reassign.
        assignable = User.objects.filter(is_active=True)
        if self.instance.pk and self.instance.assigned_to_id:
            assignable = assignable | User.objects.filter(pk=self.instance.assigned_to_id)
        self.fields["assigned_to"].queryset = assignable.distinct()
        self.fields["project"].queryset = Project.objects.filter(is_active=True)
        self.fields["project"].empty_label = "No project"


class TaskStatusForm(forms.ModelForm):
    """All a member may change about their own task."""

    class Meta:
        model = Task
        fields = ["status"]
        widgets = {"status": forms.Select(attrs=SELECT)}


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs=TEXT),
            "description": forms.Textarea(attrs={**TEXT, "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class TaskFilterForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.TextInput(attrs={**TEXT, "placeholder": "Search title"}))
    member = forms.ModelChoiceField(
        required=False, queryset=User.objects.all(), empty_label="All members",
        widget=forms.Select(attrs=SELECT),
    )
    status = forms.ChoiceField(
        required=False, choices=[("", "All statuses")] + list(Task.Status.choices),
        widget=forms.Select(attrs=SELECT),
    )
    priority = forms.ChoiceField(
        required=False, choices=[("", "All priorities")] + list(Task.Priority.choices),
        widget=forms.Select(attrs=SELECT),
    )
    due_before = forms.DateField(
        required=False, widget=forms.DateInput(attrs={**TEXT, "type": "date"})
    )

    def __init__(self, *args, **kwargs):
        # A member has no use for a "filter by member" dropdown listing everyone.
        show_member_filter = kwargs.pop("show_member_filter", True)
        super().__init__(*args, **kwargs)
        if not show_member_filter:
            del self.fields["member"]
