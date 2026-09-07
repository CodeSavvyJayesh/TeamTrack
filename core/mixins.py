"""
Authorization building blocks.

The rule this project follows everywhere:

    A member's queryset is FILTERED, not just their template.

That means a member who types /hours/42/ for someone else's record gets a 404,
not a 403. A 403 confirms the record exists; a 404 tells them nothing. Hiding a
button in a template is never the security boundary - these mixins are.
"""

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Only role=ADMIN may pass.

    Two different outcomes on purpose:

      not signed in  -> redirect to the login page with ?next=
      signed in, not an admin -> 403

    Sending an anonymous visitor to a bare 403 is just unhelpful; they may
    simply have been logged out. A signed-in member, on the other hand, has
    been told no - and should see that, not a login form they don't need.
    """

    def test_func(self):
        user = self.request.user
        return user.is_authenticated and user.is_admin_user

    @property
    def raise_exception(self):
        return self.request.user.is_authenticated


class AdminOnlyWriteMixin:
    """
    Belt-and-braces guard for views that only an admin may ever POST to.

    Used on the work-hours create/update/delete views. AdminRequiredMixin
    already covers this; this mixin exists so that the single most important
    rule in the brief - members never write their own hours - is enforced in
    two independent places rather than one.
    """

    def dispatch(self, request, *args, **kwargs):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if not (request.user.is_authenticated and request.user.is_admin_user):
                raise PermissionDenied("Only an administrator may change this record.")
        return super().dispatch(request, *args, **kwargs)


class PageTitleMixin:
    """Passes `page_title` into the template so base.html can render a header."""

    page_title = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("page_title", self.page_title)
        return context
