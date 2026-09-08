"""
The one function the rest of the app calls to tell someone something.

    notify(user, Notification.Kind.TASK_ASSIGNED, "...", url=..., target=task)

It creates the in-app notification and, when asked, sends the email too. It
never raises: failing to notify must not roll back the thing being notified
about. Assigning a task must succeed even if the mail server is down.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

from .models import Notification

logger = logging.getLogger(__name__)


def notify(
    recipient,
    kind,
    title,
    body="",
    url="",
    target=None,
    send_email=False,
    email_template=None,
    email_context=None,
    email_subject=None,
):
    """
    Create a notification. Returns it, or None if something went wrong.

    send_email      - also email the recipient
    email_template  - path to a plain-text template; falls back to `body`
    """
    if recipient is None or not getattr(recipient, "pk", None):
        return None

    try:
        target_model, target_id = "", None
        if target is not None:
            target_model = target.__class__.__name__
            target_id = getattr(target, "pk", None)

        notification = Notification.objects.create(
            recipient=recipient,
            kind=kind,
            title=title[:200],
            body=body,
            url=url,
            target_model=target_model,
            target_id=target_id,
        )
    except Exception:  # pragma: no cover - notifying must never break the action
        logger.exception("Could not create notification for %s", recipient)
        return None

    if send_email and recipient.email:
        _send_email(notification, email_template, email_context, email_subject)

    return notification


def _send_email(notification, template, context, subject):
    """Best effort. A dead mail server must not break task assignment."""
    try:
        message = (
            render_to_string(template, context or {})
            if template
            else f"{notification.title}\n\n{notification.body}\n"
        )
        send_mail(
            subject=subject or notification.title,
            message=message,
            from_email=None,  # falls back to DEFAULT_FROM_EMAIL
            recipient_list=[notification.recipient.email],
            fail_silently=False,
        )
        notification.emailed = True
        notification.save(update_fields=["emailed"])
    except Exception:
        logger.warning(
            "Could not email notification %s to %s",
            notification.pk,
            notification.recipient.email,
            exc_info=True,
        )


def notify_task_assigned(task, request=None, reassigned=False):
    """
    Tell someone they have new work, with the deadline in it.

    Called when a task is created and when it changes hands. The email carries
    an absolute link so it works from a phone, not just the machine that sent it.
    """
    path = reverse("work:task_detail", args=[task.pk])
    absolute_url = request.build_absolute_uri(path) if request else path

    kind = (
        Notification.Kind.TASK_REASSIGNED if reassigned else Notification.Kind.TASK_ASSIGNED
    )
    deadline = task.deadline_display

    body_lines = [f"Priority: {task.get_priority_display()}"]
    if deadline:
        body_lines.append(f"Deadline: {deadline}")
    if task.estimated_hours:
        body_lines.append(f"Estimated: {task.estimated_hours_display}")
    if task.project:
        body_lines.append(f"Project: {task.project.name}")

    return notify(
        recipient=task.assigned_to,
        kind=kind,
        title=f"New assignment: {task.title}",
        body=" · ".join(body_lines),
        url=path,
        target=task,
        send_email=True,
        email_template="notifications/email/task_assigned.txt",
        email_context={"task": task, "url": absolute_url, "deadline": deadline},
        email_subject=f"New assignment: {task.title}",
    )
