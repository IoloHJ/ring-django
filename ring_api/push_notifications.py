import logging
import time
from pathlib import Path

import httpx
import jwt
import requests
from django.conf import settings

from .models import MobilePushDevice


logger = logging.getLogger(__name__)
_adm_token = None
_adm_token_expires_at = 0


def _alert_payload(alert):
    return {
        "alert_id": str(alert.id),
        "url": f"ringalert://alert/{alert.id}",
        "device_name": alert.device_name or "Ring camera",
        "message": alert.message or "Ring alert detected",
    }


def _send_apns(device, alert):
    key_file = getattr(settings, "RING_APNS_PRIVATE_KEY_FILE", "")
    key_id = getattr(settings, "RING_APNS_KEY_ID", "")
    team_id = getattr(settings, "RING_APNS_TEAM_ID", "")
    bundle_id = getattr(settings, "RING_APNS_BUNDLE_ID", "")
    if not all((key_file, key_id, team_id, bundle_id)):
        return False

    private_key = Path(key_file).read_text()
    issued_at = int(time.time())
    token = jwt.encode(
        {"iss": team_id, "iat": issued_at},
        private_key,
        algorithm="ES256",
        headers={"kid": key_id},
    )
    host = (
        "api.push.apple.com"
        if settings.RING_APNS_PRODUCTION
        else "api.sandbox.push.apple.com"
    )
    with httpx.Client(http2=True, timeout=15) as client:
        response = client.post(
            f"https://{host}/3/device/{device.token}",
            headers={
                "authorization": f"bearer {token}",
                "apns-topic": bundle_id,
                "apns-push-type": "alert",
                "apns-priority": "10",
            },
            json={
                "aps": {
                    "alert": {
                        "title": alert.device_name or "Ring alert",
                        "body": alert.message or "Motion detected",
                    },
                    "sound": "default",
                },
                **_alert_payload(alert),
            },
        )
    if response.status_code == 410:
        device.active = False
        device.save(update_fields=["active", "updated_at"])
    if response.status_code >= 300:
        logger.warning("APNs rejected device %s: %s", device.id, response.text[:500])
        return False
    return True


def _adm_access_token():
    global _adm_token, _adm_token_expires_at
    if _adm_token and time.time() < _adm_token_expires_at:
        return _adm_token

    client_id = getattr(settings, "RING_ADM_CLIENT_ID", "")
    client_secret = getattr(settings, "RING_ADM_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return None

    response = requests.post(
        "https://api.amazon.com/auth/O2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "messaging:push",
        },
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    _adm_token = payload["access_token"]
    _adm_token_expires_at = time.time() + int(payload.get("expires_in", 3600)) - 60
    return _adm_token


def _send_adm(device, alert):
    access_token = _adm_access_token()
    if not access_token:
        return False

    response = requests.post(
        f"https://api.amazon.com/messaging/registrations/{device.token}/messages",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Amzn-Type-Version": "com.amazon.device.messaging.ADMMessage@1.0",
            "X-Amzn-Accept-Type": "com.amazon.device.messaging.ADMSendResult@1.0",
        },
        json={
            "data": _alert_payload(alert),
            "priority": "high",
            "consolidationKey": "ring-alert",
            "expiresAfter": 300,
        },
        timeout=15,
    )
    if response.status_code == 400 and "Unregistered" in response.text:
        device.active = False
        device.save(update_fields=["active", "updated_at"])
    if response.status_code >= 300:
        logger.warning("ADM rejected device %s: %s", device.id, response.text[:500])
        return False
    return True


def send_alert_push(alert):
    """Best-effort push delivery; a provider outage must not reject Ring webhooks."""
    for device in MobilePushDevice.objects.filter(active=True):
        try:
            if device.provider == "apns":
                _send_apns(device, alert)
            elif device.provider == "adm":
                _send_adm(device, alert)
        except Exception:
            logger.exception("Push delivery failed for device %s", device.id)
