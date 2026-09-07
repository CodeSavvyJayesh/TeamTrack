"""Upload form with real validation - size, extension, and a filename sanity check."""

import os

from django import forms
from django.conf import settings

from accounts.models import User
from work.models import Project, Task

from .models import UploadedFile

TEXT = {"class": "form-control"}
SELECT = {"class": "form-select"}


class UploadedFileForm(forms.ModelForm):
    class Meta:
        model = UploadedFile
        fields = ["file", "description", "related_task", "project", "visibility"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "description": forms.TextInput(attrs={**TEXT, "placeholder": "What is this file?"}),
            "related_task": forms.Select(attrs=SELECT),
            "project": forms.Select(attrs=SELECT),
            "visibility": forms.Select(attrs=SELECT),
        }
        help_texts = {
            "visibility": "Private means only you and administrators can open it.",
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # You can only attach a file to a task you are allowed to see.
        self.fields["related_task"].queryset = Task.objects.for_user(user) if user else Task.objects.none()
        self.fields["related_task"].empty_label = "Not related to a task"
        self.fields["project"].queryset = Project.objects.filter(is_active=True)
        self.fields["project"].empty_label = "No project"

        # ADMIN_ONLY is an administrative classification, not something a
        # member should be able to apply to their own upload.
        if user is not None and not user.is_admin_user:
            self.fields["visibility"].choices = [
                choice for choice in UploadedFile.Visibility.choices
                if choice[0] != UploadedFile.Visibility.ADMIN_ONLY
            ]

    def clean_file(self):
        uploaded = self.cleaned_data["file"]

        if uploaded.size > settings.MAX_UPLOAD_SIZE_BYTES:
            raise forms.ValidationError(
                f"That file is {uploaded.size / (1024 * 1024):.1f} MB. "
                f"The limit is {settings.MAX_UPLOAD_SIZE_MB} MB."
            )
        if uploaded.size == 0:
            raise forms.ValidationError("That file is empty.")

        extension = os.path.splitext(uploaded.name)[1].lower().lstrip(".")
        if extension not in settings.ALLOWED_UPLOAD_EXTENSIONS:
            allowed = ", ".join(settings.ALLOWED_UPLOAD_EXTENSIONS)
            raise forms.ValidationError(
                f".{extension or '(no extension)'} files are not accepted. Allowed: {allowed}."
            )
        return uploaded

    def save(self, commit=True):
        instance = super().save(commit=False)
        uploaded = self.cleaned_data["file"]

        # Metadata is captured from the upload, never trusted from a form field.
        instance.original_name = os.path.basename(uploaded.name)[:255]
        instance.content_type = (getattr(uploaded, "content_type", "") or "")[:100]
        instance.size_bytes = uploaded.size

        if commit:
            instance.save()
        return instance


class FileFilterForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.TextInput(attrs={**TEXT, "placeholder": "Search file name"}))
    member = forms.ModelChoiceField(
        required=False, queryset=User.objects.all(), empty_label="All members",
        widget=forms.Select(attrs=SELECT),
    )
    extension = forms.CharField(
        required=False, widget=forms.TextInput(attrs={**TEXT, "placeholder": "pdf, xlsx..."})
    )

    def __init__(self, *args, **kwargs):
        show_member_filter = kwargs.pop("show_member_filter", True)
        super().__init__(*args, **kwargs)
        if not show_member_filter:
            del self.fields["member"]
