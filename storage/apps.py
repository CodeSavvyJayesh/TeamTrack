from django.apps import AppConfig


class StorageConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "storage"
    verbose_name = "Files"

    def ready(self):
        from . import signals  # noqa: F401  (removes the file from disk on delete)
