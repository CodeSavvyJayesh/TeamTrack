from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm

from .models import Invitation, MemberProfile, User


class MemberProfileInline(admin.StackedInline):
    model = MemberProfile
    can_delete = False
    extra = 0


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Rebuilt for an email-based user with no username field."""

    change_password_form = AdminPasswordChangeForm
    inlines = [MemberProfileInline]
    ordering = ["full_name"]
    list_display = ["email", "full_name", "role", "is_active", "date_joined"]
    list_filter = ["role", "is_active", "is_staff"]
    search_fields = ["email", "full_name"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Identity", {"fields": ("full_name", "role")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "full_name", "role", "password1", "password2"),
        }),
    )


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ["email", "full_name", "status", "invited_by", "created_at", "expires_at"]
    list_filter = ["accepted_at"]
    search_fields = ["email", "full_name"]
    readonly_fields = ["token", "created_at", "accepted_at"]


@admin.register(MemberProfile)
class MemberProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "work_type", "department", "tracks_google_forms"]
    list_filter = ["work_type", "department", "tracks_google_forms"]
    search_fields = ["user__full_name", "user__email"]
