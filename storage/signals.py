"""
Keep the disk in step with the database.

Django deliberately does NOT delete the file behind a FileField when the row
goes away - that would be dangerous if two rows ever shared a path. Ours never
do (upload_path gives every upload a uuid4 name), so without this handler
MEDIA_ROOT grows forever and deleted files stay readable on disk.
"""

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import UploadedFile


@receiver(post_delete, sender=UploadedFile)
def delete_file_from_disk(sender, instance, **kwargs):
    if not instance.file:
        return
    # save=False: the row is already gone, there is nothing left to update.
    instance.file.delete(save=False)
