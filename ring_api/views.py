import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from django.shortcuts import render
import requests

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import RingToken, RingWebhookEvent


logger = logging.getLogger(__name__)


# ============================================================
# CONFIG
# ============================================================

RING_TOKEN_URL = getattr(
    settings,
    "RING_OAUTH_URL",
    "https://oauth.ring.com/oauth/token",
)

RING_API_BASE = getattr(
    settings,
    "RING_API_BASE",
    "https://api.amazonvision.com",
)

RING_CLIENT_ID = getattr(
    settings,
    "RING_CLIENT_ID",
    "",
)

RING_CLIENT_SECRET = getattr(
    settings,
    "RING_CLIENT_SECRET",
    "",
)

RING_HMAC_SIGNING_KEY = getattr(
    settings,
    "RING_HMAC_SIGNING_KEY",
    "",
)


# ============================================================
# RING DEVICE DISCOVERY
# ============================================================

def ring_devices(request):
    """
    Return Ring devices available to the authenticated account.
    """

    if request.method != "GET":
        return JsonResponse(
            {"error": "GET required"},
            status=405,
        )

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

    url = (
        f"{settings.RING_API_BASE}"
        "/v1/devices"
        "?include=status,capabilities"
    )

    try:
        response = requests.get(
            url,
            headers={
                "Authorization": (
                    f"Bearer {token.access_token}"
                ),
                "Accept": "application/vnd.api+json",
            },
            timeout=20,
        )

        logger.info(
            "Ring devices response HTTP %s",
            response.status_code,
        )

    except requests.RequestException:
        logger.exception(
            "Ring device discovery request failed"
        )

        return JsonResponse(
            {
                "error": "ring_request_failed",
            },
            status=502,
        )

    if response.status_code != 200:
        logger.error(
            "Ring devices API error: %s",
            response.text[:1000],
        )

        return JsonResponse(
            {
                "error": "ring_api_error",
                "status": response.status_code,
                "details": response.text,
            },
            status=502,
        )

    try:
        payload = response.json()
    except ValueError:
        return JsonResponse(
            {
                "error": "invalid_ring_response",
            },
            status=502,
        )

    return JsonResponse(payload)


# ============================================================
# LIVE VIEW PAGE
# ============================================================

def ring_live_page(request):
    """
    Browser UI for selecting a Ring device and viewing live video.
    """

    return render(
        request,
        "live.html",
    )


# ============================================================
# START WHEP LIVE SESSION
# ============================================================

@csrf_exempt
def ring_live_start(request, device_id):
    """
    Proxy the browser's WebRTC SDP offer to Ring WHEP.

    Ring requires the authenticated API request to be
    server-to-server, so the browser must not call
    api.amazonvision.com directly.
    """

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST required"},
            status=405,
        )

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
        "Starting Ring live session for device %s",
        device_id,
    )

    url = (
        f"{settings.RING_API_BASE}"
        f"/v1/devices/{device_id}"
        "/media/streaming/whep/sessions"
    )

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
            "Ring WHEP response HTTP %s",
            response.status_code,
        )

    except requests.RequestException:
        logger.exception(
            "Ring WHEP request failed"
        )

        return JsonResponse(
            {
                "error": "ring_whep_request_failed",
            },
            status=502,
        )

    if response.status_code != 201:
        logger.error(
            "Ring WHEP error: %s",
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

    session_url = response.headers.get(
        "Location"
    )

    if not session_url:
        logger.error(
            "Ring WHEP response missing Location header"
        )

        return JsonResponse(
            {
                "error": "missing_session_url",
            },
            status=502,
        )

    return HttpResponse(
        response.text,
        content_type="application/sdp",
        status=201,
        headers={
            "X-Ring-Session-URL": session_url,
        },
    )


# ============================================================
# STOP WHEP LIVE SESSION
# ============================================================

@csrf_exempt
def ring_live_stop(request, device_id):
    """
    Close an active Ring WHEP session.
    """

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST required"},
            status=405,
        )

    token = (
        RingToken.objects
        .order_by("-updated_at")
        .first()
    )

    if not token:
        return JsonResponse(
            {
                "error": "no_ring_token",
            },
            status=401,
        )

    session_url = request.POST.get(
        "session_url"
    )

    if not session_url:
        try:
            body = json.loads(
                request.body.decode("utf-8")
            )

            session_url = body.get(
                "session_url"
            )

        except Exception:
            pass

    if not session_url:
        return JsonResponse(
            {
                "error": "missing_session_url",
            },
            status=400,
        )

    # Security check:
    #
    # Only allow deletion of Ring API sessions.
    #
    if not session_url.startswith(
        settings.RING_API_BASE
    ):
        return JsonResponse(
            {
                "error": "invalid_session_url",
            },
            status=400,
        )

    try:
        response = requests.delete(
            session_url,
            headers={
                "Authorization": (
                    f"Bearer {token.access_token}"
                ),
            },
            timeout=20,
        )

        logger.info(
            "Ring WHEP DELETE response HTTP %s",
            response.status_code,
        )

    except requests.RequestException:
        logger.exception(
            "Ring WHEP session deletion failed"
        )

        return JsonResponse(
            {
                "error": "ring_whep_delete_failed",
            },
            status=502,
        )

    return JsonResponse(
        {
            "status": "stopped",
            "ring_status": response.status_code,
        }
    )

# ============================================================
# HOME
# ============================================================

def home(request):
    return JsonResponse(
        {
            "service": "Ring Django Integration",
            "status": "online",
            "domain": getattr(
                settings,
                "RING_PUBLIC_URL",
                "",
            ),
        }
    )


# ============================================================
# RING API HELPERS
# ============================================================

def ring_headers(access_token):
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def safe_json(response):
    try:
        return response.json()
    except ValueError:
        return {}


# ============================================================
# TOKEN EXCHANGE
# ============================================================

@csrf_exempt
@require_POST
def ring_token(request):
    """
    Ring calls this endpoint server-to-server.

    POST /ring/token/

    Expected fields:

        code
        client_id

    We exchange the code for:

        access_token
        refresh_token

    Then immediately call:

        GET /v1/users/me

    to obtain the Ring Account ID.

    The tokens are stored in RingToken.
    """

    logger.info(
        "Ring token exchange request received"
    )

    logger.info(
        "Ring token exchange content type: %s",
        request.content_type,
    )

    logger.info(
        "Ring token exchange fields: %s",
        list(request.POST.keys()),
    )

    code = request.POST.get("code")
    client_id = request.POST.get("client_id")

    if not code:
        logger.error(
            "Ring token exchange missing code"
        )

        return JsonResponse(
            {
                "error": "missing_code",
            },
            status=400,
        )

    if not client_id:
        logger.error(
            "Ring token exchange missing client_id"
        )

        return JsonResponse(
            {
                "error": "missing_client_id",
            },
            status=400,
        )

    if not RING_CLIENT_ID:
        logger.error(
            "RING_CLIENT_ID is not configured"
        )

        return JsonResponse(
            {
                "error": "server_configuration_error",
            },
            status=500,
        )

    if not RING_CLIENT_SECRET:
        logger.error(
            "RING_CLIENT_SECRET is not configured"
        )

        return JsonResponse(
            {
                "error": "server_configuration_error",
            },
            status=500,
        )

    # --------------------------------------------------------
    # Verify Ring client ID
    # --------------------------------------------------------

    if not hmac.compare_digest(
        client_id,
        RING_CLIENT_ID,
    ):
        logger.error(
            "Invalid Ring client_id"
        )

        return JsonResponse(
            {
                "error": "invalid_client",
            },
            status=401,
        )

    # --------------------------------------------------------
    # Exchange authorization code
    # --------------------------------------------------------

    logger.info(
        "Exchanging Ring authorization code"
    )

    payload = {
        "grant_type": "authorization_code",
        "client_id": RING_CLIENT_ID,
        "client_secret": RING_CLIENT_SECRET,
        "code": code,
    }

    try:
        response = requests.post(
            RING_TOKEN_URL,
            data=payload,
            headers={
                "Content-Type":
                    "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=20,
        )

    except requests.RequestException:
        logger.exception(
            "Ring OAuth request failed"
        )

        return JsonResponse(
            {
                "error": "ring_oauth_unavailable",
            },
            status=502,
        )

    logger.info(
        "Ring OAuth response HTTP %s",
        response.status_code,
    )

    if response.status_code != 200:

        error_data = safe_json(response)

        logger.error(
            "Ring OAuth exchange failed: %s",
            {
                key: value
                for key, value in error_data.items()
                if key in (
                    "error",
                    "error_description",
                )
            },
        )

        return JsonResponse(
            {
                "error": "token_exchange_failed",
            },
            status=502,
        )

    token_data = safe_json(response)

    access_token = token_data.get(
        "access_token"
    )

    refresh_token = token_data.get(
        "refresh_token"
    )

    token_type = token_data.get(
        "token_type",
        "Bearer",
    )

    scope = token_data.get(
        "scope",
        "",
    )

    expires_in = token_data.get(
        "expires_in",
        0,
    )

    if not access_token:
        logger.error(
            "Ring response missing access_token"
        )

        return JsonResponse(
            {
                "error":
                    "missing_access_token",
            },
            status=502,
        )

    if not refresh_token:
        logger.error(
            "Ring response missing refresh_token"
        )

        return JsonResponse(
            {
                "error":
                    "missing_refresh_token",
            },
            status=502,
        )

    # --------------------------------------------------------
    # Retrieve Ring Account ID
    # --------------------------------------------------------

    logger.info(
        "Retrieving Ring Account ID"
    )

    try:
        user_response = requests.get(
            f"{RING_API_BASE}/v1/users/me",
            headers=ring_headers(
                access_token
            ),
            timeout=20,
        )

    except requests.RequestException:
        logger.exception(
            "Ring /v1/users/me request failed"
        )

        return JsonResponse(
            {
                "error":
                    "ring_user_lookup_failed",
            },
            status=502,
        )

    logger.info(
        "Ring /v1/users/me response HTTP %s",
        user_response.status_code,
    )

    if user_response.status_code != 200:

        logger.error(
            "Ring /v1/users/me failed"
        )

        return JsonResponse(
            {
                "error":
                    "ring_user_lookup_failed",
            },
            status=502,
        )

    user_data = safe_json(
        user_response
    )

    # JSON:API:
    #
    # {
    #     "data": {
    #         "id": "..."
    #     }
    # }

    account_id = (
        user_data
        .get("data", {})
        .get("id")
    )

    if not account_id:

        logger.error(
            "Ring Account ID not found"
        )

        return JsonResponse(
            {
                "error":
                    "missing_ring_account_id",
            },
            status=502,
        )

    logger.info(
        "Ring Account ID received"
    )

    # --------------------------------------------------------
    # Store token
    # --------------------------------------------------------

    token, created = RingToken.objects.update_or_create(
        account_id=account_id,
        defaults={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": token_type,
            "scope": scope,
            "expires_in": expires_in,
        },
    )

    logger.info(
        "Ring token stored successfully. created=%s",
        created,
    )

    # --------------------------------------------------------
    # IMPORTANT
    #
    # Do NOT return access_token or refresh_token.
    # --------------------------------------------------------

    return JsonResponse(
        {
            "status": "ok",
        },
        status=200,
    )


# ============================================================
# RING ACCOUNT LINK
# ============================================================

@require_GET
def ring_link(request):
    """
    Ring calls:

        GET /ring/link/?nonce=...&time=...

    The nonce is matched against the stored Ring Account ID.

    IMPORTANT:
    Your current Django project does not yet have a partner
    login/account model tied to RingToken, so this endpoint
    performs the Ring-side nonce validation first.

    Once this is working we can associate RingToken with
    request.user.
    """

    logger.info(
        "Ring account-link request received"
    )

    nonce = request.GET.get(
        "nonce"
    )

    time_value = request.GET.get(
        "time"
    )

    if not nonce:
        return JsonResponse(
            {
                "error":
                    "missing_nonce",
            },
            status=400,
        )

    if not time_value:
        return JsonResponse(
            {
                "error":
                    "missing_time",
            },
            status=400,
        )

    logger.info(
        "Ring account-link nonce received"
    )

    # --------------------------------------------------------
    # Validate timestamp
    # --------------------------------------------------------

    try:
        timestamp_ms = int(
            time_value
        )

    except (TypeError, ValueError):

        return JsonResponse(
            {
                "error":
                    "invalid_time",
            },
            status=400,
        )

    now_ms = int(
        time.time() * 1000
    )

    # Ring's nonce is time-bound.
    #
    # We use a 10-minute validation window.
    #

    if abs(
        now_ms - timestamp_ms
    ) > 10 * 60 * 1000:

        logger.warning(
            "Ring account-link request expired"
        )

        return JsonResponse(
            {
                "error":
                    "expired_link",
            },
            status=400,
        )

    # --------------------------------------------------------
    # HMAC key
    # --------------------------------------------------------

    if not RING_HMAC_SIGNING_KEY:

        logger.error(
            "RING_HMAC_SIGNING_KEY is not configured"
        )

        return JsonResponse(
            {
                "error":
                    "server_configuration_error",
            },
            status=500,
        )

    # --------------------------------------------------------
    # Find matching Ring token
    # --------------------------------------------------------

    matching_token = None

    tokens = RingToken.objects.all()

    for token in tokens:

        account_id = token.account_id

        # Ring nonce generation:
        #
        # HMAC-SHA256(
        #     HMAC signing key,
        #     timestamp:account_id
        # )
        #

        message = (
            f"{time_value}:{account_id}"
        )

        digest = hmac.new(
            RING_HMAC_SIGNING_KEY.encode(
                "utf-8"
            ),
            message.encode(
                "utf-8"
            ),
            hashlib.sha256,
        ).digest()

        expected_nonce = (
            base64.urlsafe_b64encode(
                digest
            )
            .rstrip(b"=")
            .decode("utf-8")
        )

        if hmac.compare_digest(
            expected_nonce,
            nonce,
        ):
            matching_token = token
            break

    if not matching_token:

        logger.warning(
            "No RingToken matched supplied nonce"
        )

        return JsonResponse(
            {
                "error":
                    "ring_account_not_found",
            },
            status=404,
        )

    logger.info(
        "Ring Account matched successfully"
    )

    # --------------------------------------------------------
    # Complete App Integration
    # --------------------------------------------------------

    access_token = (
        matching_token.access_token
    )

    integration_url = (
        f"{RING_API_BASE}"
        "/v1/accounts/me/app-integrations"
    )

    headers = ring_headers(
        access_token
    )

    # --------------------------------------------------------
    # POST integration
    # --------------------------------------------------------

    logger.info(
        "Calling Ring App Integrations POST"
    )

    try:

        post_response = requests.post(
            integration_url,
            headers=headers,
            json={
                "nonce": nonce,
            },
            timeout=20,
        )

    except requests.RequestException:

        logger.exception(
            "Ring App Integration POST failed"
        )

        return JsonResponse(
            {
                "error":
                    "ring_integration_failed",
            },
            status=502,
        )

    logger.info(
        "Ring App Integration POST HTTP %s",
        post_response.status_code,
    )

    if post_response.status_code not in (
        200,
        201,
        204,
    ):

        logger.error(
            "Ring App Integration POST rejected"
        )

        return JsonResponse(
            {
                "error":
                    "ring_integration_rejected",
            },
            status=502,
        )

    # --------------------------------------------------------
    # PATCH integration -> completed
    # --------------------------------------------------------

    logger.info(
        "Completing Ring App Integration"
    )

    try:

        patch_response = requests.patch(
            integration_url,
            headers=headers,
            json={
                "status": "completed",
            },
            timeout=20,
        )

    except requests.RequestException:

        logger.exception(
            "Ring App Integration PATCH failed"
        )

        return JsonResponse(
            {
                "error":
                    "ring_integration_completion_failed",
            },
            status=502,
        )

    logger.info(
        "Ring App Integration PATCH HTTP %s",
        patch_response.status_code,
    )

    if patch_response.status_code not in (
        200,
        201,
        204,
    ):

        logger.error(
            "Ring App Integration PATCH rejected"
        )

        return JsonResponse(
            {
                "error":
                    "ring_integration_completion_failed",
            },
            status=502,
        )

    logger.info(
        "Ring account linking completed successfully"
    )

    return JsonResponse(
        {
            "status": "completed",
            "message":
                "Ring account linked successfully",
        },
        status=200,
    )


# ============================================================
# RING CALLBACK
# ============================================================

def ring_callback(request):
    """
    This is NOT used by the current one-way Ring flow.

    Kept here because your project already has the URL.

    Never display the authorization code.
    """

    if request.GET.get("error"):

        return HttpResponse(
            "Ring authorization failed.",
            status=400,
        )

    code = request.GET.get(
        "code"
    )

    if not code:

        return HttpResponse(
            "No authorization code received.",
            status=400,
        )

    logger.info(
        "Ring browser callback received"
    )

    return HttpResponse(
        "Ring authorization callback received successfully."
    )


# ============================================================
# RING USER
# ============================================================

@require_GET
def ring_user(request):

    token = (
        RingToken.objects
        .order_by("-updated_at")
        .first()
    )

    if not token:

        return JsonResponse(
            {
                "error":
                    "No Ring token stored",
            },
            status=404,
        )

    try:

        response = requests.get(
            f"{RING_API_BASE}/v1/users/me",
            headers=ring_headers(
                token.access_token
            ),
            timeout=20,
        )

    except requests.RequestException:

        logger.exception(
            "Ring user request failed"
        )

        return JsonResponse(
            {
                "error":
                    "Ring API unavailable",
            },
            status=502,
        )

    data = safe_json(
        response
    )

    return JsonResponse(
        {
            "status_code":
                response.status_code,
            "data":
                data,
        },
        status=response.status_code,
    )


# ============================================================
# RING DEVICES
# ============================================================

@require_GET
def ring_devices(request):

    token = (
        RingToken.objects
        .order_by("-updated_at")
        .first()
    )

    if not token:

        return JsonResponse(
            {
                "error":
                    "No Ring token stored",
            },
            status=404,
        )

    try:

        response = requests.get(
            f"{RING_API_BASE}/v1/devices",
            headers=ring_headers(
                token.access_token
            ),
            timeout=20,
        )

    except requests.RequestException:

        logger.exception(
            "Ring device request failed"
        )

        return JsonResponse(
            {
                "error":
                    "Ring API unavailable",
            },
            status=502,
        )

    data = safe_json(
        response
    )

    return JsonResponse(
        {
            "status_code":
                response.status_code,
            "data":
                data,
        },
        status=response.status_code,
    )


# ============================================================
# RING WEBHOOK
# ============================================================

@csrf_exempt
@require_POST
def ring_webhook(request):

    logger.info(
        "Ring webhook received"
    )

    try:

        raw_body = request.body

        logger.info(
            "Webhook payload size: %s bytes",
            len(raw_body),
        )

        payload = json.loads(
            raw_body.decode("utf-8")
        )

    except Exception:

        logger.exception(
            "Invalid webhook JSON"
        )

        return JsonResponse(
            {
                "error":
                    "Invalid JSON",
            },
            status=400,
        )

    request_id = (
        request.headers.get(
            "X-Request-ID"
        )
        or request.headers.get(
            "X-Request-Id"
        )
        or secrets.token_hex(16)
    )

    event_type = (
        request.headers.get(
            "X-Event-Type",
            "",
        )
    )

    RingWebhookEvent.objects.update_or_create(
        request_id=request_id,
        defaults={
            "event_type": event_type,
            "payload": payload,
        },
    )

    logger.info(
        "Ring webhook stored: %s",
        request_id,
    )

    return JsonResponse(
        {
            "status":
                "received",
        }
    )