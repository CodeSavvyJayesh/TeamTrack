from django.urls import path

from . import views

app_name = "members"

urlpatterns = [
    path("", views.MemberListView.as_view(), name="list"),
    path("invite/", views.MemberInviteView.as_view(), name="invite"),
    path("invitations/", views.InvitationListView.as_view(), name="invitations"),
    path("invitations/<int:pk>/resend/", views.InvitationResendView.as_view(), name="invitation_resend"),
    path("<int:pk>/", views.MemberDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.MemberUpdateView.as_view(), name="edit"),
    path("<int:pk>/toggle-active/", views.MemberToggleActiveView.as_view(), name="toggle_active"),
]
