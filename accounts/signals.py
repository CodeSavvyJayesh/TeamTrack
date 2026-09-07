"""Every user gets a MemberProfile, so `user.profile` never raises."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import MemberProfile, User


@receiver(post_save, sender=User)
def create_member_profile(sender, instance, created, **kwargs):
    if created:
        MemberProfile.objects.get_or_create(user=instance)
