from django.apps import AppConfig


class GoogleFormsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations.google"
    label = "google_forms"
    verbose_name = "Google Forms integration"
