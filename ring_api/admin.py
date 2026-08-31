from django.contrib import admin

from .models import (
    RingToken,
    RingWebhookEvent,
)


@admin.register(RingToken)
class RingTokenAdmin(admin.ModelAdmin):

    list_display = (
        "account_id",
        "token_type",
        "expires_in",
        "created_at",
        "updated_at",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )


@admin.register(RingWebhookEvent)
class RingWebhookEventAdmin(admin.ModelAdmin):

    list_display = (
        "request_id",
        "event_type",
        "account_id",
        "received_at",
    )

    readonly_fields = (
        "received_at",
    )