from django.contrib import admin

from .models import AppInstallation, SecurityProfile


@admin.register(SecurityProfile)
class SecurityProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "totp_enabled", "updated_at")
    search_fields = ("user__username", "user__email")


@admin.register(AppInstallation)
class AppInstallationAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "installation_id",
        "platform",
        "app_version",
        "activated_at",
        "last_seen_at",
        "deactivated_at",
    )
    list_filter = ("platform", "deactivated_at")
    search_fields = ("user__username", "installation_id", "token_prefix")
