"""Forms for signing in, accepting an invitation, and editing your own profile."""

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import MemberProfile, User


class EmailLoginForm(AuthenticationForm):
    """Same behaviour as Django's, relabelled because we log in by email."""

    username = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email",
                                       "class": "form-control", "placeholder": "you@example.com"}),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password",
                                          "class": "form-control"}),
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "That email and password don't match an active account.",
        "inactive": "This account has been deactivated. Contact your administrator.",
    }


class InvitationAcceptForm(forms.Form):
    """
    Sets the password for a brand-new account.

    Not a ModelForm: the User does not exist yet when this form is displayed,
    and we never want a form field that could write to `role`.
    """

    password1 = forms.CharField(
        label="Choose a password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "class": "form-control"}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "class": "form-control"}),
    )

    def clean_password2(self):
        p1 = self.cleaned_data.get("password1")
        p2 = self.cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise ValidationError("The two passwords don't match.")
        validate_password(p2)  # runs AUTH_PASSWORD_VALIDATORS
        return p2


class SelfProfileForm(forms.ModelForm):
    """
    What a member may change about themselves: contact details only.

    Note what is absent - work_type, department, notes and tracks_google_forms
    are administrative fields. Because they are not on the form, a crafted POST
    cannot set them.
    """

    full_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"class": "form-control"}))

    class Meta:
        model = MemberProfile
        fields = ["phone"]
        widgets = {"phone": forms.TextInput(attrs={"class": "form-control"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["full_name"].initial = self.instance.user.full_name

    def save(self, commit=True):
        profile = super().save(commit=commit)
        user = profile.user
        user.full_name = self.cleaned_data["full_name"]
        if commit:
            user.save(update_fields=["full_name"])
        return profile
