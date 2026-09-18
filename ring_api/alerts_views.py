import json
import logging
import re
from html import escape
from pathlib import Path

import requests

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from .alert_processing import parse_ring_timestamp
from .models import MobilePushDevice, RingAlert, RingToken
from security.services import app_installation_from_request


logger = logging.getLogger(__name__)

MOBILE_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


# ============================================================
# HELPERS
# ============================================================

def get_latest_ring_token():
    return (
        RingToken.objects
        .order_by("-updated_at")
        .first()
    )


def get_ring_access_token():
    token = get_latest_ring_token()

    if not token:
        raise RuntimeError(
            "No Ring account is linked."
        )

    return token.access_token


def mobile_releases():
    """Return configured releases with safe, basename-only artifact names."""
    releases = []
    for release in getattr(settings, "RING_MOBILE_RELEASES", []):
        version = str(release.get("version", ""))
        if not MOBILE_VERSION_PATTERN.fullmatch(version):
            continue
        releases.append({
            "version": version,
            "android": Path(str(release.get("android", ""))).name,
            "ios": Path(str(release.get("ios", ""))).name,
        })
    return releases


def configured_mobile_release(version):
    return next(
        (
            release
            for release in mobile_releases()
            if release["version"] == version
        ),
        None,
    )


def mobile_artifact_path(platform, version):
    release = configured_mobile_release(version)
    if not release or platform not in ("android", "ios"):
        return None

    filename = release[platform]
    if not filename:
        return None

    release_dir = Path(settings.RING_MOBILE_RELEASE_DIR).resolve()
    artifact = (release_dir / filename).resolve()
    if artifact.parent != release_dir:
        return None
    return artifact


def ring_mobile_install(request):
    return render(
        request,
        "mobile_install.html",
        {"releases": mobile_releases()},
    )


def ring_mobile_download(request, platform, version):
    artifact = mobile_artifact_path(platform, version)
    if not artifact or not artifact.is_file():
        return JsonResponse({"error": "mobile_release_not_found"}, status=404)

    content_type = (
        "application/vnd.android.package-archive"
        if platform == "android"
        else "application/octet-stream"
    )
    return FileResponse(
        artifact.open("rb"),
        as_attachment=True,
        filename=artifact.name,
        content_type=content_type,
    )


def ring_mobile_ios_manifest(request, version):
    release = configured_mobile_release(version)
    artifact = mobile_artifact_path("ios", version)
    if not release or not artifact:
        return HttpResponse("Release not found", status=404)

    ipa_url = request.build_absolute_uri(
        f"/ring/mobile/ios/{version}/download/"
    )
    bundle_id = escape(settings.RING_MOBILE_IOS_BUNDLE_ID)
    version_text = escape(version)
    manifest = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>items</key><array><dict><key>assets</key><array><dict>
<key>kind</key><string>software-package</string>
<key>url</key><string>{escape(ipa_url)}</string>
</dict></array><key>metadata</key><dict>
<key>bundle-identifier</key><string>{bundle_id}</string>
<key>bundle-version</key><string>{version_text}</string>
<key>kind</key><string>software</string>
<key>title</key><string>Ring Alert Viewer</string>
</dict></dict></array></dict></plist>"""
    return HttpResponse(manifest, content_type="application/xml")


@csrf_exempt
def ring_mobile_push_register(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        body = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "invalid_json"}, status=400)

    provider = str(body.get("provider", ""))
    token = str(body.get("token", "")).strip()
    platform = str(body.get("platform", "")).strip()
    if provider not in ("apns", "adm") or not token:
        return JsonResponse({"error": "provider_and_token_required"}, status=400)

    installation = app_installation_from_request(request)
    if not installation:
        return JsonResponse({"error": "invalid_app_token"}, status=401)

    device, _ = MobilePushDevice.objects.update_or_create(
        token=token,
        defaults={
            "provider": provider,
            "platform": platform,
            "active": True,
            "installation": installation,
        },
    )
    return JsonResponse({"registered": True, "id": device.id})


def alert_device_name(alert):
    """
    Get the best possible device name from the alert.

    We deliberately keep this independent from the
    existing history implementation.
    """

    name = (
        getattr(alert, "device_name", None)
        or ""
    ).strip()

    if name:
        return name

    return "Ring camera"


def serialise_alert(alert):
    return {
        "id": alert.id,

        "event_id": (
            getattr(alert, "event_id", None)
            or ""
        ),

        "device_id": (
            getattr(alert, "device_id", None)
            or ""
        ),

        "device_name": alert_device_name(alert),

        "event_type": (
            getattr(alert, "event_type", None)
            or "motion"
        ),

        "message": (
            getattr(alert, "message", None)
            or ""
        ),

        "timestamp": (
            alert.timestamp.isoformat()
            if getattr(alert, "timestamp", None)
            else None
        ),

        "created_at": (
            alert.created_at.isoformat()
            if getattr(alert, "created_at", None)
            else None
        ),

        "read": bool(
            getattr(alert, "read", False)
        ),
    }


def populate_alert_device_names(alerts):
    """Fill missing alert names from the linked Ring device list."""
    missing_alerts = [
        alert
        for alert in alerts
        if alert.device_id
        and alert.device_name in ("", "Unknown Device")
    ]

    if not missing_alerts:
        return

    token = get_latest_ring_token()
    if not token or not token.access_token:
        return

    try:
        response = requests.get(
            f"{settings.RING_API_BASE.rstrip('/')}/v1/devices",
            headers={
                "Authorization": f"Bearer {token.access_token}",
                "Accept": "application/vnd.api+json",
            },
            timeout=10,
        )
        response.raise_for_status()
        devices = response.json().get("data", [])
    except (requests.RequestException, ValueError) as exc:
        logger.warning("[ALERTS] Unable to load device names: %s", exc)
        return

    names = {}
    for device in devices:
        device_id = device.get("id")
        attributes = device.get("attributes") or {}
        name = (
            attributes.get("description")
            or attributes.get("name")
            or attributes.get("device_name")
            or attributes.get("nickname")
        )
        if device_id and name:
            names[str(device_id)] = str(name)

    for alert in missing_alerts:
        name = names.get(str(alert.device_id))
        if not name:
            continue

        alert.device_name = name
        alert.save(update_fields=["device_name"])


# ============================================================
# ALERTS PAGE
# ============================================================

@login_required
def ring_alerts_page(request):
    """
    Completely standalone Alerts page.

    IMPORTANT:
    This page does NOT use the existing history
    or live implementation.
    """

    return render(
        request,
        "alerts.html",
    )


# ============================================================
# ALERTS API
# ============================================================

@require_GET
def ring_alerts_api(request):
    """
    GET /ring/alerts/api/

    Returns recent alerts.

    The frontend polls this endpoint for new alerts.
    """

    try:

        alerts = (
            RingAlert.objects
            .order_by("-timestamp", "-created_at")
            [:50]
        )

        alerts = list(alerts)
        populate_alert_device_names(alerts)

        results = [
            serialise_alert(alert)
            for alert in alerts
        ]

        return JsonResponse(
            {
                "success": True,
                "alerts": results,
            }
        )

    except Exception as exc:

        logger.exception(
            "[ALERTS] Failed loading alerts"
        )

        return JsonResponse(
            {
                "success": False,
                "error": "alerts_load_failed",
                "details": str(exc),
            },
            status=500,
        )


@require_GET
def ring_alert_video(request, alert_id):
    """Return the Ring recording associated with a stored alert."""
    try:
        alert = RingAlert.objects.get(id=alert_id)
    except RingAlert.DoesNotExist:
        return JsonResponse(
            {"error": "alert_not_found"},
            status=404,
        )

    if not alert.device_id or not alert.timestamp:
        return JsonResponse(
            {
                "error": "alert_video_unavailable",
                "message": "This alert has no recording timestamp or device.",
            },
            status=404,
        )

    event = (alert.payload or {}).get("event") or {}
    attributes = event.get("attributes") or {}
    end = parse_ring_timestamp(attributes.get("end"))
    duration_ms = 60_000

    if end and end > alert.timestamp:
        duration_ms = int(
            (end - alert.timestamp).total_seconds() * 1000
        )

    duration_ms = min(max(duration_ms, 1_000), 15 * 60 * 1000)
    start_timestamp = int(alert.timestamp.timestamp() * 1000)
    url = (
        f"{settings.RING_API_BASE.rstrip('/')}/v1/devices/"
        f"{alert.device_id}/media/video/download"
    )
    payload = {
        "timestamp": start_timestamp,
        "duration": duration_ms,
        "video_options": {
            "codec": "avc",
            "frame_rate": 25,
            "resolution": {"width": 1920, "height": 1080},
        },
        "audio_options": {"audio_enabled": True},
    }

    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {get_ring_access_token()}",
                "Content-Type": "application/json",
                "Accept": "video/mp4",
            },
            json=payload,
            timeout=120,
        )
    except (requests.RequestException, RuntimeError) as exc:
        logger.exception("[ALERT VIDEO] Ring media request failed")
        return JsonResponse(
            {
                "error": "ring_alert_video_request_failed",
                "details": str(exc),
            },
            status=502,
        )

    if response.status_code not in (200, 206):
        return JsonResponse(
            {
                "error": "ring_alert_video_api_error",
                "status_code": response.status_code,
                "details": response.text[:3000],
            },
            status=response.status_code,
        )

    video_response = HttpResponse(
        response.content,
        content_type=response.headers.get("Content-Type", "video/mp4"),
        status=response.status_code,
    )
    video_response["Accept-Ranges"] = "bytes"

    for header_name in (
        "Content-Length",
        "Content-Range",
        "X-Media-Length",
        "X-Media-Duration",
        "X-Request-ID",
    ):
        value = response.headers.get(header_name)
        if value:
            video_response[header_name] = value

    return video_response


# ============================================================
# SINGLE ALERT
# ============================================================

@require_GET
def ring_alert_detail(request, alert_id):
    """
    GET /ring/alerts/<alert_id>/
    """

    try:

        alert = RingAlert.objects.get(
            id=alert_id
        )

    except RingAlert.DoesNotExist:

        return JsonResponse(
            {
                "success": False,
                "error": "alert_not_found",
            },
            status=404,
        )

    return JsonResponse(
        {
            "success": True,
            "alert": serialise_alert(alert),
        }
    )


# ============================================================
# ALERT LIVE START
# ============================================================

# ============================================================
# ALERT LIVE START
# ============================================================





@csrf_exempt
def ring_alert_live_start(request, device_id):
    """
    Start a Ring live stream from an alert.

    The alert supplies the Ring device_id.
    This intentionally uses the exact same WHEP
    implementation as the normal live page.
    """

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST required"},
            status=405,
        )

    # ---------------------------------------------------------
    # GET RING TOKEN
    # ---------------------------------------------------------

    token = (
        RingToken.objects
        .order_by("-updated_at")
        .first()
    )

    if not token:
        return JsonResponse(
            {
                "error": "no_ring_token",
                "message": "No Ring account is linked.",
            },
            status=401,
        )

    # ---------------------------------------------------------
    # GET SDP OFFER FROM BROWSER
    # ---------------------------------------------------------

    if not request.body:
        return JsonResponse(
            {
                "error": "missing_sdp",
            },
            status=400,
        )

    sdp_offer = request.body.decode(
        "utf-8",
        errors="replace",
    )

    logger.info(
        "Starting ALERT Ring live session for device %s",
        device_id,
    )

    # ---------------------------------------------------------
    # EXACT SAME WHEP URL AS WORKING LIVE PAGE
    # ---------------------------------------------------------

    url = (
        f"{settings.RING_API_BASE}"
        f"/v1/devices/{device_id}"
        "/media/streaming/whep/sessions"
    )

    logger.info(
        "ALERT WHEP URL: %s",
        url,
    )

    logger.info(
        "ALERT WHEP DEVICE ID: %s",
        device_id,
    )

    logger.info(
        "ALERT WHEP TOKEN PRESENT: %s",
        bool(token.access_token),
    )

    # ---------------------------------------------------------
    # SEND SDP OFFER TO RING
    # ---------------------------------------------------------

    try:

        response = requests.post(
            url,
            headers={
                "Authorization": (
                    f"Bearer {token.access_token}"
                ),
                "Content-Type": "application/sdp",
                "Accept": "application/sdp",
            },
            data=sdp_offer,
            timeout=30,
        )

        logger.info(
            "ALERT Ring WHEP response HTTP %s",
            response.status_code,
        )

    except requests.RequestException:

        logger.exception(
            "ALERT Ring WHEP request failed"
        )

        return JsonResponse(
            {
                "error": "ring_whep_request_failed",
            },
            status=502,
        )

    # ---------------------------------------------------------
    # RING MUST RETURN 201
    # ---------------------------------------------------------

    if response.status_code != 201:

        logger.error(
            "ALERT Ring WHEP error: %s",
            response.text[:2000],
        )

        return JsonResponse(
            {
                "error": "ring_whep_error",
                "status": response.status_code,
                "details": response.text,
            },
            status=502,
        )

    # ---------------------------------------------------------
    # GET WHEP SESSION LOCATION
    # ---------------------------------------------------------

    session_url = response.headers.get(
        "Location"
    )

    if not session_url:

        logger.error(
            "ALERT Ring WHEP response missing Location header"
        )

        return JsonResponse(
            {
                "error": "missing_session_url",
            },
            status=502,
        )

    logger.info(
        "ALERT Ring WHEP session URL: %s",
        session_url,
    )

    # ---------------------------------------------------------
    # RETURN RING SDP TO BROWSER
    # ---------------------------------------------------------

    return HttpResponse(
        response.text,
        content_type="application/sdp",
        status=201,
        headers={
            "X-Ring-Alert-Session-URL": session_url,
        },
    )



    # --------------------------------------------------------
    # Find
    # ============================================================
# ALERT LIVE STOP
# ============================================================

@csrf_exempt
def ring_alert_live_stop(request, alert_id):
    """
    Stop the dedicated live WHEP session for an alert.

    IMPORTANT:
    This is completely separate from the existing
    /ring/live/ implementation.
    """

    if request.method != "POST":
        return JsonResponse(
            {
                "error": "POST required",
            },
            status=405,
        )

    # --------------------------------------------------------
    # Check alert exists
    # --------------------------------------------------------

    try:
        alert = RingAlert.objects.get(
            id=alert_id
        )

    except RingAlert.DoesNotExist:

        return JsonResponse(
            {
                "error": "alert_not_found",
            },
            status=404,
        )

    # --------------------------------------------------------
    # Get Ring token
    # --------------------------------------------------------

    token = (
        RingToken.objects
        .order_by("-updated_at")
        .first()
    )

    if not token:

        return JsonResponse(
            {
                "error": "no_ring_token",
                "message": "No Ring account is linked.",
            },
            status=401,
        )

    # --------------------------------------------------------
    # Get session URL
    # --------------------------------------------------------

    session_url = request.POST.get(
        "session_url"
    )

    # Also support JSON requests
    if not session_url:

        try:

            body = json.loads(
                request.body.decode(
                    "utf-8"
                )
            )

            session_url = body.get(
                "session_url"
            )

        except (
            json.JSONDecodeError,
            UnicodeDecodeError,
        ):

            pass

    if not session_url:

        return JsonResponse(
            {
                "error": "missing_session_url",
            },
            status=400,
        )

    # --------------------------------------------------------
    # Security check
    # --------------------------------------------------------

    ring_base = (
        settings.RING_API_BASE
        or ""
    ).rstrip("/")

    if not session_url.startswith(
        ring_base
    ):

        logger.warning(
            "[ALERT LIVE] Rejected invalid session URL: %s",
            session_url,
        )

        return JsonResponse(
            {
                "error": "invalid_session_url",
            },
            status=400,
        )

    # --------------------------------------------------------
    # Delete WHEP session
    # --------------------------------------------------------

    logger.info(
        "[ALERT LIVE] Stopping alert session: alert=%s",
        alert.id,
    )

    logger.info(
        "[ALERT LIVE] Session URL: %s",
        session_url,
    )

    try:

        response = requests.delete(
            session_url,
            headers={
                "Authorization": (
                    f"Bearer {token.access_token}"
                ),
                "Accept": "application/json",
            },
            timeout=20,
        )

    except requests.RequestException as exc:

        logger.exception(
            "[ALERT LIVE] WHEP DELETE failed"
        )

        return JsonResponse(
            {
                "error": "ring_alert_whep_delete_failed",
                "details": str(exc),
            },
            status=502,
        )

    logger.info(
        "[ALERT LIVE] Stop response HTTP %s",
        response.status_code,
    )

    # --------------------------------------------------------
    # Return result
    # --------------------------------------------------------

    return JsonResponse(
        {
            "status": "stopped",
            "alert_id": alert.id,
            "ring_status": response.status_code,
        }
    )
