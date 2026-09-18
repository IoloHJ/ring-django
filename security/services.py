import hashlib
import secrets

from django.utils import timezone

from .models import AppInstallation


def hash_app_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_app_installation(user, installation_id, platform, app_version):
    raw_token = secrets.token_urlsafe(48)
    installation, _ = AppInstallation.objects.update_or_create(
        user=user,
        installation_id=installation_id,
        defaults={
            "token_hash": hash_app_token(raw_token),
            "token_prefix": raw_token[:12],
            "platform": platform,
            "app_version": app_version,
            "deactivated_at": None,
        },
    )
    return installation, raw_token


def app_installation_from_request(request):
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    if not token:
        return None
    installation = AppInstallation.objects.filter(
        token_hash=hash_app_token(token),
        deactivated_at__isnull=True,
    ).select_related("user").first()
    if installation:
        installation.last_seen_at = timezone.now()
        installation.save(update_fields=["last_seen_at"])
    return installation
