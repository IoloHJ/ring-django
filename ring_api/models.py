from django.db import models


class RingToken(models.Model):

    account_id = models.CharField(
        max_length=255,
        unique=True,
    )

    access_token = models.TextField()

    refresh_token = models.TextField()

    token_type = models.CharField(
        max_length=50,
        default="Bearer",
    )

    scope = models.TextField(
        blank=True,
        default="",
    )

    expires_in = models.IntegerField(
        default=0,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return self.account_id


class RingOAuthSession(models.Model):
    state = models.CharField(
        max_length=255,
        unique=True
    )

    code_verifier = models.CharField(
        max_length=255
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.state


class RingWebhookEvent(models.Model):

    request_id = models.CharField(
        max_length=255,
        unique=True,
    )

    account_id = models.CharField(
        max_length=255,
        blank=True,
    )

    event_type = models.CharField(
        max_length=255,
        blank=True,
    )

    payload = models.JSONField()

    received_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return (
            f"{self.event_type} "
            f"{self.request_id}"
        )


class RingAlert(models.Model):
    event_id = models.CharField(
        max_length=255,
        unique=True,
    )

    device_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    device_name = models.CharField(
        max_length=255,
        blank=True,
        default="Unknown Device",
    )

    event_type = models.CharField(
        max_length=100,
        blank=True,
        default="unknown",
    )

    message = models.CharField(
        max_length=500,
        blank=True,
        default="Ring event detected",
    )

    timestamp = models.DateTimeField(
        null=True,
        blank=True,
    )

    payload = models.JSONField(
        default=dict,
        blank=True,
    )

    read = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.device_name} - "
            f"{self.event_type}"
        )


class MobilePushDevice(models.Model):
    PROVIDER_CHOICES = (
        ("apns", "Apple Push Notification service"),
        ("adm", "Amazon Device Messaging"),
    )

    provider = models.CharField(max_length=10, choices=PROVIDER_CHOICES)
    token = models.TextField(unique=True)
    installation = models.ForeignKey(
        "security.AppInstallation",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="push_devices",
    )
    platform = models.CharField(max_length=20, blank=True, default="")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.provider}:{self.platform}:{self.token[:12]}"
