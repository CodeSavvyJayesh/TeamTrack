"""Admin-facing forms for inviting and editing members."""

from django import forms

from accounts.models import Invitation, MemberProfile, User

TEXT = {"class": "form-control"}
SELECT = {"class": "form-select"}
CHECK = {"class": "form-check-input"}


class InvitationForm(forms.ModelForm):
    """
    'Add member' from the admin's point of view. It creates an Invitation, not
    a User - the account only exists once the person sets their own password.
    """

    class Meta:
        model = Invitation
        fields = ["full_name", "email", "work_type", "department", "tracks_google_forms"]
        widgets = {
            "full_name": forms.TextInput(attrs={**TEXT, "placeholder": "Full name"}),
            "email": forms.EmailInput(attrs={**TEXT, "placeholder": "name@example.com"}),
            "work_type": forms.TextInput(attrs={**TEXT, "placeholder": "Operations, Developer, Research..."}),
            "department": forms.TextInput(attrs=TEXT),
            "tracks_google_forms": forms.CheckboxInput(attrs=CHECK),
        }
        help_texts = {
            "work_type": "Free text. It only labels the person - it never changes what the app does.",
            "tracks_google_forms": "Tick only if this person's work involves Google Forms.",
        }

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Someone with this email already has an account.")
        pending = Invitation.objects.pending().filter(email=email)
        if self.instance.pk:
            pending = pending.exclude(pk=self.instance.pk)
        if pending.exists():
            raise forms.ValidationError(
                "There is already a pending invitation for this email. Resend it instead."
            )
        return email


class MemberUpdateForm(forms.ModelForm):
    """
    Admin editing an existing member.

    `role` is intentionally absent. Promoting someone to administrator is not a
    routine edit, so it is left to /django-admin/ where it is deliberate.
    """

    full_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs=TEXT))
    email = forms.EmailField(widget=forms.EmailInput(attrs=TEXT))

    class Meta:
        model = MemberProfile
        fields = ["work_type", "department", "phone", "joined_on", "notes", "tracks_google_forms"]
        widgets = {
            "work_type": forms.TextInput(attrs=TEXT),
            "department": forms.TextInput(attrs=TEXT),
            "phone": forms.TextInput(attrs=TEXT),
            "joined_on": forms.DateInput(attrs={**TEXT, "type": "date"}),
            "notes": forms.Textarea(attrs={**TEXT, "rows": 3}),
            "tracks_google_forms": forms.CheckboxInput(attrs=CHECK),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["full_name"].initial = self.instance.user.full_name
        self.fields["email"].initial = self.instance.user.email

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email=email).exclude(pk=self.instance.user_id).exists():
            raise forms.ValidationError("Another account already uses this email.")
        return email

    def save(self, commit=True):
        profile = super().save(commit=commit)
        user = profile.user
        user.full_name = self.cleaned_data["full_name"]
        user.email = self.cleaned_data["email"]
        if commit:
            user.save(update_fields=["full_name", "email"])
        return profile


class MemberFilterForm(forms.Form):
    """Search and filter for the member list. All fields optional."""

    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={**TEXT, "placeholder": "Search name or email"}),
    )
    work_type = forms.CharField(required=False, widget=forms.TextInput(attrs={**TEXT, "placeholder": "Work type"}))
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All statuses"), ("active", "Active"), ("inactive", "Inactive")],
        widget=forms.Select(attrs=SELECT),
    )
