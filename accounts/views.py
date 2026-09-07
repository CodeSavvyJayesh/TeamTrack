"""Sign in, sign out, accept an invitation, view and edit your own profile."""

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import DetailView, FormView, TemplateView, UpdateView

from core.mixins import PageTitleMixin
from core.models import ActivityLog
from core.services import log_activity

from .forms import EmailLoginForm, InvitationAcceptForm, SelfProfileForm
from .models import Invitation, MemberProfile, User


class AppLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True


class AppLogoutView(LogoutView):
    next_page = reverse_lazy("accounts:login")


class InvitationAcceptView(FormView):
    """
    The public end of the invitation flow.

    Everything about the new account comes from the Invitation row, never from
    the request, so a visitor with a valid token still cannot choose their own
    name, work type, or - crucially - their role.
    """

    template_name = "accounts/invitation_accept.html"
    form_class = InvitationAcceptForm

    def dispatch(self, request, *args, **kwargs):
        self.invitation = Invitation.objects.filter(token=kwargs.get("token")).first()

        if self.invitation is None:
            return self._reject("This invitation link is not valid.")
        if self.invitation.is_accepted:
            return self._reject("This invitation has already been used. Try signing in instead.")
        if self.invitation.is_expired:
            return self._reject("This invitation has expired. Ask your administrator to resend it.")
        if User.objects.filter(email=self.invitation.email).exists():
            return self._reject("An account already exists for this email address.")

        return super().dispatch(request, *args, **kwargs)

    def _reject(self, reason):
        messages.error(self.request, reason)
        return redirect("accounts:invitation_invalid")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["invitation"] = self.invitation
        return context

    @transaction.atomic
    def form_valid(self, form):
        invitation = self.invitation

        user = User.objects.create_user(
            email=invitation.email,
            password=form.cleaned_data["password2"],
            full_name=invitation.full_name,
            role=User.Role.MEMBER,
            is_active=True,
        )

        profile = user.profile  # created by the post_save signal
        profile.work_type = invitation.work_type
        profile.department = invitation.department
        profile.tracks_google_forms = invitation.tracks_google_forms
        profile.joined_on = timezone.localdate()
        profile.save()

        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["accepted_at"])

        log_activity(
            actor=user,
            verb=ActivityLog.Verb.MEMBER_ACTIVATED,
            target=user,
            subject=user,
            target_repr=f"{user.full_name} accepted their invitation",
        )

        messages.success(self.request, "Your account is ready. Please sign in.")
        return redirect("accounts:login")


class InvitationInvalidView(PageTitleMixin, TemplateView):
    """
    Dead end for a bad, used or expired token.

    Deliberately says little: it never confirms whether the token existed, who
    it was for, or why exactly it failed. All three answers would help someone
    fishing for valid invitation links.
    """

    template_name = "accounts/invitation_invalid.html"
    page_title = "Invitation problem"


class ProfileView(LoginRequiredMixin, PageTitleMixin, DetailView):
    template_name = "accounts/profile.html"
    context_object_name = "profile"
    page_title = "My profile"

    def get_object(self, queryset=None):
        return self.request.user.profile

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["recent_activity"] = ActivityLog.objects.filter(
            subject=self.request.user
        ).select_related("actor")[:10]
        return context


class ProfileEditView(LoginRequiredMixin, PageTitleMixin, UpdateView):
    """A member may edit their own name and phone. Nothing else."""

    template_name = "accounts/profile_form.html"
    form_class = SelfProfileForm
    model = MemberProfile
    success_url = reverse_lazy("accounts:profile")
    page_title = "Edit my profile"

    def get_object(self, queryset=None):
        return self.request.user.profile

    def form_valid(self, form):
        messages.success(self.request, "Your profile has been updated.")
        return super().form_valid(form)
