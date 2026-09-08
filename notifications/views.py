"""
Notification views.

Everything is scoped to request.user by queryset, so there is no way to read,
open or dismiss somebody else's notification.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView

from core.mixins import PageTitleMixin

from .models import Notification


class NotificationListView(LoginRequiredMixin, PageTitleMixin, ListView):
    template_name = "notifications/notification_list.html"
    context_object_name = "notifications"
    paginate_by = 30
    page_title = "Notifications"

    def get_queryset(self):
        return Notification.objects.for_user(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["unread_total"] = (
            Notification.objects.for_user(self.request.user).unread().count()
        )
        return context


class NotificationOpenView(LoginRequiredMixin, View):
    """
    Marks one notification read and forwards to whatever it points at.

    Doing both in one step means a member never has to think about "reading"
    a notification - opening the work is what dismisses it.
    """

    def get(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
        notification.mark_read()
        return redirect(notification.url or "notifications:list")


class MarkAllReadView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request):
        count = Notification.objects.for_user(request.user).unread().mark_all_read()
        if count:
            messages.success(request, f"Marked {count} notification{'s' if count != 1 else ''} as read.")
        return redirect("notifications:list")
