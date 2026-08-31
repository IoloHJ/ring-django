import json
import logging

import requests

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from .models import RingAlert, RingToken


logger = logging.getLogger(__name__)


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


# ============================================================
# ALERTS PAGE
# ============================================================

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
            .order_by("-created_at")
            [:50]
        )

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