"""
Administrator-facing member management.

Every view here is AdminRequiredMixin. There is no member-visible URL in this
app at all, which is why it is separate from `accounts`.
"""

import logging

from django.contrib import messages
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from accounts.models import Invitation, MemberProfile, User
from core.mixins import AdminRequiredMixin, PageTitleMixin
from core.models import ActivityLog
from core.services import log_activity
from hours.models import WorkSession
from hours.selectors import daily_series, totals_for, week_bounds
from integrations.ether.config import notify_ether
from integrations.google.models import FormSubmissionStat
from reports.models import DailyReport
from storage.models import UploadedFile
from work.models import Task

from .forms import InvitationForm, MemberFilterForm, MemberUpdateForm

logger = logging.getLogger(__name__)


def send_invitation_email(invitation, request):
    """
    Returns True if the message was handed to the mail server, False if it was
    not. Never raises.

    The invitation record is the valuable thing; the email is only delivery.
    Letting an SMTP failure escape used to roll the invitation back and return
    a 500, which left the administrator with nothing to resend and no way to
    tell a dead mail server from a real bug. Now the invitation survives, the
    reason is logged, and the caller offers the link to share by hand.

    In development this prints to the terminal (console email backend), so the
    whole invite flow is testable without an SMTP server.
    """
    context = {"invitation": invitation, "accept_url": invitation.get_accept_url(request)}
    body = render_to_string("members/email/invitation.txt", context)
    try:
        send_mail(
            subject="You have been invited to TeamTrack",
            message=body,
            from_email=None,  # falls back to DEFAULT_FROM_EMAIL
            recipient_list=[invitation.email],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Could not email the invitation to %s", invitation.email)
        return False


def _invitation_sent_message(request, invitation, delivered):
    """The same feedback for a new invitation and a resent one."""
    if delivered:
        days = (invitation.expires_at - timezone.now()).days + 1
        messages.success(
            request,
            f"Invitation sent to {invitation.email}. It expires in {days} days.",
        )
    else:
        messages.warning(
            request,
            f"{invitation.full_name}'s invitation was created, but the email "
            f"could not be sent - check the email settings. Use Copy link on "
            f"the invitations list to send it to {invitation.email} yourself.",
        )


class MemberListView(AdminRequiredMixin, PageTitleMixin, ListView):
    template_name = "members/member_list.html"
    context_object_name = "members"
    paginate_by = 25
    page_title = "Members"

    def get_queryset(self):
        queryset = (
            User.objects.filter(role=User.Role.MEMBER)
            .select_related("profile")
            .annotate(
                open_tasks=Count("tasks", filter=~Q(tasks__status=Task.Status.COMPLETED), distinct=True),
                done_tasks=Count("tasks", filter=Q(tasks__status=Task.Status.COMPLETED), distinct=True),
            )
            .order_by("full_name")
        )
        self.filter_form = MemberFilterForm(self.request.GET or None)
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data.get("q"):
                queryset = queryset.filter(
                    Q(full_name__icontains=data["q"]) | Q(email__icontains=data["q"])
                )
            if data.get("work_type"):
                queryset = queryset.filter(profile__work_type__icontains=data["work_type"])
            if data.get("status") == "active":
                queryset = queryset.filter(is_active=True)
            elif data.get("status") == "inactive":
                queryset = queryset.filter(is_active=False)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        today = timezone.localdate()
        # Today's minutes per member, in one query rather than one per row.
        context["today_minutes"] = {
            row["member_id"]: row["total"]
            for row in WorkSession.objects.filter(date=today)
            .values("member_id")
            .annotate(total=Sum("duration_minutes"))
        }
        context["pending_invitations"] = Invitation.objects.pending().count()
        return context


class MemberDetailView(AdminRequiredMixin, PageTitleMixin, DetailView):
    """
    One page that works identically for every member.

    Whatever is not relevant to this person simply has no rows - there is no
    branch anywhere on who they are or what they do.
    """

    template_name = "members/member_detail.html"
    context_object_name = "member"
    # Only members. /members/<an admin pk>/ is not a page that should exist.
    queryset = User.objects.filter(role=User.Role.MEMBER).select_related("profile")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = self.object

        context["page_title"] = member.full_name
        context["totals"] = totals_for(member)

        tasks = Task.objects.filter(assigned_to=member)
        context["task_counts"] = {
            "total": tasks.count(),
            "completed": tasks.filter(status=Task.Status.COMPLETED).count(),
            "in_progress": tasks.filter(status=Task.Status.IN_PROGRESS).count(),
            "pending": tasks.filter(status=Task.Status.PENDING).count(),
            "blocked": tasks.filter(status=Task.Status.BLOCKED).count(),
        }
        context["recent_tasks"] = tasks.select_related("project")[:8]
        context["recent_sessions"] = WorkSession.objects.filter(member=member)[:8]
        context["recent_reports"] = DailyReport.objects.filter(member=member)[:5]
        context["recent_files"] = UploadedFile.objects.filter(uploaded_by=member)[:8]
        context["activity"] = ActivityLog.objects.filter(subject=member).select_related("actor")[:12]

        labels, values = daily_series(member=member, days=7)
        context["chart_labels"] = labels
        context["chart_values"] = values

        # Google Forms rows only exist for members whose profile enables them.
        if member.profile.tracks_google_forms:
            stats = FormSubmissionStat.objects.filter(form__member=member)
            week_start, _ = week_bounds()
            month_start = timezone.localdate().replace(day=1)
            context["form_stats"] = {
                "today": stats.filter(date=timezone.localdate()).total_submissions(),
                "week": stats.filter(date__gte=week_start).total_submissions(),
                "month": stats.filter(date__gte=month_start).total_submissions(),
            }
            context["tracked_forms"] = member.tracked_forms.all()
        return context


class MemberInviteView(AdminRequiredMixin, PageTitleMixin, CreateView):
    template_name = "members/invitation_form.html"
    form_class = InvitationForm
    success_url = reverse_lazy("members:invitations")
    page_title = "Invite a member"

    def form_valid(self, form):
        # The invitation and its log entry commit together. The email is sent
        # afterwards, deliberately outside the transaction: a mail server that
        # is down must not undo the invitation.
        with transaction.atomic():
            invitation = form.save(commit=False)
            invitation.invited_by = self.request.user
            invitation.save()
            log_activity(
                actor=self.request.user,
                verb=ActivityLog.Verb.MEMBER_INVITED,
                target=invitation,
                target_repr=f"Invited {invitation.full_name} ({invitation.email})",
            )

        delivered = send_invitation_email(invitation, self.request)
        _invitation_sent_message(self.request, invitation, delivered)
        return redirect(self.success_url)


class MemberUpdateView(AdminRequiredMixin, PageTitleMixin, UpdateView):
    template_name = "members/member_form.html"
    form_class = MemberUpdateForm
    model = MemberProfile
    page_title = "Edit member"

    def get_object(self, queryset=None):
        return get_object_or_404(MemberProfile, user_id=self.kwargs["pk"])

    def get_success_url(self):
        return reverse_lazy("members:detail", args=[self.object.user_id])

    def form_valid(self, form):
        response = super().form_valid(form)
        log_activity(
            actor=self.request.user,
            verb=ActivityLog.Verb.MEMBER_UPDATED,
            target=self.object.user,
            subject=self.object.user,
            target_repr=f"Updated {self.object.user.full_name}'s details",
        )
        messages.success(self.request, "Member updated.")
        return response


class MemberToggleActiveView(AdminRequiredMixin, View):
    """
    Deactivate or reactivate. Never deletes - historical records stay intact
    and Django's auth backend refuses login for is_active=False on its own.
    """

    def post(self, request, pk):
        member = get_object_or_404(User, pk=pk, role=User.Role.MEMBER)

        member.is_active = not member.is_active
        member.save(update_fields=["is_active"])

        if member.is_active:
            verb, word, event = ActivityLog.Verb.MEMBER_REACTIVATED, "reactivated", "member.activated"
        else:
            verb, word, event = ActivityLog.Verb.MEMBER_DEACTIVATED, "deactivated", "member.deactivated"

        log_activity(
            actor=request.user, verb=verb, target=member, subject=member,
            target_repr=f"{member.full_name} {word}",
        )
        notify_ether(event, {"member_id": member.pk})
        messages.success(request, f"{member.full_name} has been {word}.")
        return redirect("members:detail", pk=member.pk)


class InvitationListView(AdminRequiredMixin, PageTitleMixin, ListView):
    template_name = "members/invitation_list.html"
    context_object_name = "invitations"
    paginate_by = 25
    page_title = "Invitations"

    def get_queryset(self):
        return Invitation.objects.select_related("invited_by")


class InvitationResendView(AdminRequiredMixin, View):
    """Issues a fresh token and expiry, invalidating the old link."""

    def post(self, request, pk):
        invitation = get_object_or_404(Invitation, pk=pk)
        if invitation.is_accepted:
            messages.warning(request, "That invitation has already been accepted.")
            return redirect("members:invitations")

        invitation.refresh_token()
        log_activity(
            actor=request.user,
            verb=ActivityLog.Verb.MEMBER_INVITED,
            target=invitation,
            target_repr=f"Resent invitation to {invitation.email}",
        )
        delivered = send_invitation_email(invitation, request)
        _invitation_sent_message(request, invitation, delivered)
        return redirect("members:invitations")
