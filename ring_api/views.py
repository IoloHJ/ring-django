import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from django.shortcuts import render
import requests
import logging
import requests
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
import os
import requests

from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET
from django.conf import settings

from .models import RingToken, RingWebhookEvent
from .alert_processing import create_alert_from_payload


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

    alert, alert_created = create_alert_from_payload(payload)

    if alert_created:
        logger.info(
            "Ring alert created: %s",
            alert.event_id,
        )
    elif alert is None:
        logger.warning(
            "Ring webhook has no alert event ID: %s",
            request_id,
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

# ============================================================================
# RING HISTORY
# ============================================================================

# ============================================================================
# RING HISTORY
# ============================================================================

RING_API_BASE = "https://api.amazonvision.com"

def get_ring_access_token():
    """
    Return the current Ring access token.

    If the stored token is expired or close to expiry, refresh it
    automatically using the stored Ring refresh token.

    This is shared by the Ring API views so live, alerts, history,
    recordings, etc. can all use the same authentication mechanism.
    """

    import os
    from datetime import timedelta

    import requests

    from django.utils import timezone

    # ------------------------------------------------------------
    # Find the most recently updated Ring token
    # ------------------------------------------------------------

    try:
        token = (
            RingToken.objects
            .order_by("-updated_at")
            .first()
        )
    except Exception as exc:
        print(
            "[RING AUTH] Database token lookup failed:",
            repr(exc),
        )
        token = None

    # ------------------------------------------------------------
    # No database token
    # ------------------------------------------------------------

    if not token:
        fallback = (
            os.getenv("RING_ACCESS_TOKEN")
            or os.getenv("AVA_ACCESS_TOKEN")
            or os.getenv("ACCESS_TOKEN")
        )

        if fallback:
            print(
                "[RING AUTH] Using access token from environment"
            )
            return fallback

        raise RuntimeError(
            "No Ring access token is available."
        )

    # ------------------------------------------------------------
    # Check whether the access token is still valid
    # ------------------------------------------------------------

    now = timezone.now()

    token_is_valid = False

    if (
        token.access_token
        and token.expires_in
        and token.created_at
    ):
        expires_at = (
            token.created_at
            + timedelta(seconds=token.expires_in)
        )

        # Refresh five minutes before expiry.
        refresh_at = (
            expires_at
            - timedelta(seconds=300)
        )

        if now < refresh_at:
            token_is_valid = True

    # ------------------------------------------------------------
    # Valid token
    # ------------------------------------------------------------

    if token_is_valid:
        return token.access_token

    # ------------------------------------------------------------
    # Token expired / close to expiry
    # ------------------------------------------------------------

    print(
        "[RING AUTH] Access token expired or close to expiry."
    )

    if not token.refresh_token:
        raise RuntimeError(
            "Ring access token has expired and no refresh token "
            "is available."
        )

    client_id = os.getenv("RING_CLIENT_ID")
    client_secret = os.getenv("RING_CLIENT_SECRET")

    if not client_id:
        raise RuntimeError(
            "RING_CLIENT_ID is not configured."
        )

    if not client_secret:
        raise RuntimeError(
            "RING_CLIENT_SECRET is not configured."
        )

    token_url = os.getenv(
        "RING_TOKEN_URL",
        "https://oauth.ring.com/oauth/token",
    )

    # ------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------

    try:
        response = requests.post(
            token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": token.refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={
                "Accept": "application/json",
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        print(
            "[RING AUTH] Token refresh request failed:",
            repr(exc),
        )

        raise RuntimeError(
            "Unable to contact Ring OAuth server."
        )

    # ------------------------------------------------------------
    # Ring rejected refresh
    # ------------------------------------------------------------

    if response.status_code != 200:
        print(
            "[RING AUTH] Token refresh failed:",
            response.status_code,
            response.text[:500],
        )

        raise RuntimeError(
            f"Ring token refresh failed "
            f"(HTTP {response.status_code})."
        )

    try:
        data = response.json()
    except ValueError:
        raise RuntimeError(
            "Ring returned an invalid token response."
        )

    new_access_token = data.get("access_token")

    if not new_access_token:
        raise RuntimeError(
            "Ring token response did not contain access_token."
        )

    # ------------------------------------------------------------
    # Save new access token
    # ------------------------------------------------------------

    token.access_token = new_access_token

    # Ring can rotate refresh tokens.
    # Always save the new one when supplied.
    if data.get("refresh_token"):
        token.refresh_token = data["refresh_token"]

    if data.get("token_type"):
        token.token_type = data["token_type"]

    if data.get("scope"):
        token.scope = data["scope"]

    if data.get("expires_in") is not None:
        token.expires_in = int(data["expires_in"])

    token.save()

    print(
        "[RING AUTH] Access token refreshed successfully."
    )

    return token.access_token




def ring_api_get(url, params=None):
    """
    Make a server-side GET request to the Ring Partner API
    using the same access token as the working live integration.
    """

    access_token = get_ring_access_token()

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.api+json",
    }

    print(
        "[RING API GET]",
        url,
    )

    if params:
        print(
            "[RING API GET] Params:",
            params,
        )

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=60,
        allow_redirects=True,
    )

    print(
        "[RING API GET] HTTP:",
        response.status_code,
    )

    return response


def ring_api_post(url, payload):
    """
    Make a server-side POST request to the Ring Partner API
    using the same access token as the working live integration.
    """

    access_token = get_ring_access_token()

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "*/*",
        "Content-Type": "application/json",
    }

    print(
        "[RING API POST]",
        url,
    )

    print(
        "[RING API POST] Payload:",
        payload,
    )

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=60,
        allow_redirects=True,
    )

    print(
        "[RING API POST] HTTP:",
        response.status_code,
    )

    return response


# ============================================================================
# HISTORY PAGE
# ============================================================================

@require_GET
def ring_history(request):
    """
    Render the Ring history page.
    """

    return render(
        request,
        "history.html",
    )


# ============================================================================
# HISTORY API
# ============================================================================

@require_GET
def ring_history_api(request, device_id):
    """
    Return Ring history events for a device.

    Uses the same RingToken database authentication as the
    working /ring/devices/ and live endpoints.

    Browser:
        GET /ring/history/<device_id>/

    Ring:
        GET /v1/history/devices/<device_id>/events
    """

    print("=" * 70)
    print("[HISTORY API] Request received")
    print("[HISTORY API] Device:", device_id)

    # ------------------------------------------------------------------------
    # Get the same stored Ring token used by the working devices/live APIs
    # ------------------------------------------------------------------------

    token = (
        RingToken.objects
        .order_by("-updated_at")
        .first()
    )

    if not token:
        print("[HISTORY API] No Ring token found")

        return JsonResponse(
            {
                "error": "no_ring_token",
                "message": "No Ring account is linked.",
            },
            status=401,
        )

    access_token = token.access_token

    if not access_token:
        print("[HISTORY API] Ring token exists but access token is empty")

        return JsonResponse(
            {
                "error": "missing_access_token",
                "message": "The stored Ring access token is empty.",
            },
            status=401,
        )

    # ------------------------------------------------------------------------
    # Build Ring History API URL
    # ------------------------------------------------------------------------

    url = (
        f"{RING_API_BASE}"
        f"/v1/history/devices/{device_id}/events"
    )

    # ------------------------------------------------------------------------
    # Optional query parameters
    # ------------------------------------------------------------------------

    params = {}

    event_types = request.GET.get("event_types")

    if event_types:
        params["event_types"] = event_types

    page_key = request.GET.get("page_key")

    if page_key:
        params["page[key]"] = page_key

    print("[HISTORY API] Ring URL:", url)
    print("[HISTORY API] Params:", params)

    # ------------------------------------------------------------------------
    # IMPORTANT:
    #
    # Do NOT use ring_api_get() here because that helper is currently
    # looking for RING_ACCESS_TOKEN.
    #
    # We already have the working database token above.
    # ------------------------------------------------------------------------

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.api+json",
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=60,
            allow_redirects=True,
        )

        print(
            "[HISTORY API] Ring HTTP status:",
            response.status_code,
        )

    except requests.RequestException as exc:

        print(
            "[HISTORY API] Request exception:",
            repr(exc),
        )

        logger.exception(
            "[HISTORY API] Ring history request failed"
        )

        return JsonResponse(
            {
                "error": "ring_history_request_failed",
                "details": str(exc),
            },
            status=502,
        )

    # ------------------------------------------------------------------------
    # Handle Ring API errors
    # ------------------------------------------------------------------------

    if response.status_code != 200:

        print(
            "[HISTORY API] Ring response:",
            response.text[:3000],
        )

        return JsonResponse(
            {
                "error": "ring_history_api_error",
                "status_code": response.status_code,
                "details": response.text,
            },
            status=response.status_code,
        )

    # ------------------------------------------------------------------------
    # Decode JSON
    # ------------------------------------------------------------------------

    try:

        data = response.json()

    except ValueError:

        print(
            "[HISTORY API] Ring returned invalid JSON:"
        )

        print(
            response.text[:3000]
        )

        return JsonResponse(
            {
                "error": "invalid_ring_response",
                "details": response.text[:1000],
            },
            status=502,
        )

    # ------------------------------------------------------------------------
    # Log number of events
    # ------------------------------------------------------------------------

    events = data.get(
        "data",
        []
    )

    print(
        "[HISTORY API] Events returned:",
        len(events),
    )

    print("=" * 70)

    # ------------------------------------------------------------------------
    # Return Ring response directly to browser
    # ------------------------------------------------------------------------

    return JsonResponse(
        data,
        status=200,
    )


# ============================================================================
# HISTORY VIDEO
# ============================================================================

# ============================================================================
# HISTORY VIDEO
# ============================================================================

@require_GET
def ring_history_video(request, device_id, event_id):
    """
    Retrieve a historical Ring video clip for a history event.

    Browser:
        GET /ring/history/<device_id>/video/<event_id>/

    Ring Partner API:
        POST /v1/devices/<device_id>/media/video/download

    The Ring API returns MP4 binary media.

    The event_id is retained for logging/correlation. The actual
    media request uses the event's start timestamp and duration.
    """

    print("=" * 70)
    print("[HISTORY VIDEO] Request received")
    print("[HISTORY VIDEO] Device:", device_id)
    print("[HISTORY VIDEO] Event:", event_id)

    # ------------------------------------------------------------------------
    # Read requested time range
    # ------------------------------------------------------------------------

    start = request.GET.get("start")
    duration = request.GET.get("duration")

    print("[HISTORY VIDEO] Start:", start)
    print("[HISTORY VIDEO] Duration:", duration)

    if not start:
        return JsonResponse(
            {
                "error": "missing_start_timestamp",
                "message": "A start timestamp is required.",
            },
            status=400,
        )

    try:
        start_timestamp = int(start)

    except (TypeError, ValueError):

        return JsonResponse(
            {
                "error": "invalid_start_timestamp",
                "message": "Start timestamp must be an integer.",
            },
            status=400,
        )

    # ------------------------------------------------------------------------
    # Duration
    # ------------------------------------------------------------------------

    try:
        duration_ms = int(duration or 0)

    except (TypeError, ValueError):

        duration_ms = 0

    # Ring allows a maximum of 15 minutes.
    if duration_ms <= 0:
        duration_ms = 60_000

    duration_ms = min(
        duration_ms,
        15 * 60 * 1000,
    )

    print(
        "[HISTORY VIDEO] Requesting duration:",
        duration_ms,
        "ms",
    )

    # ------------------------------------------------------------------------
    # Ring Media Clips endpoint
    # ------------------------------------------------------------------------

    url = (
        f"{RING_API_BASE}"
        f"/v1/devices/{device_id}"
        f"/media/video/download"
    )

    print(
        "[HISTORY VIDEO] Ring URL:",
        url,
    )

    # ------------------------------------------------------------------------
    # Ring request payload
    # ------------------------------------------------------------------------

    payload = {
        "timestamp": start_timestamp,
        "duration": duration_ms,

        # Request a broadly compatible video.
        "video_options": {
            "codec": "avc",
            "frame_rate": 25,
            "resolution": {
                "width": 1920,
                "height": 1080,
            },
        },

        # Enable audio where available.
        "audio_options": {
            "audio_enabled": True,
        },
    }

    print(
        "[HISTORY VIDEO] Payload:",
        payload,
    )

    # ------------------------------------------------------------------------
    # Get working Ring token
    # ------------------------------------------------------------------------

    try:

        access_token = get_ring_access_token()

    except Exception as exc:

        print(
            "[HISTORY VIDEO] Token error:",
            repr(exc),
        )

        return JsonResponse(
            {
                "error": "ring_authentication_error",
                "details": str(exc),
            },
            status=500,
        )

    # ------------------------------------------------------------------------
    # Call Ring Media Clips API
    # ------------------------------------------------------------------------

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "video/mp4",
    }

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=120,
            allow_redirects=True,
        )

    except requests.RequestException as exc:

        print(
            "[HISTORY VIDEO] Request exception:",
            repr(exc),
        )

        logger.exception(
            "[HISTORY VIDEO] Ring media request failed"
        )

        return JsonResponse(
            {
                "error": "ring_video_request_failed",
                "details": str(exc),
            },
            status=502,
        )

    print(
        "[HISTORY VIDEO] Ring HTTP status:",
        response.status_code,
    )

    print(
        "[HISTORY VIDEO] Content-Type:",
        response.headers.get("Content-Type"),
    )

    print(
        "[HISTORY VIDEO] Content-Length:",
        response.headers.get("Content-Length"),
    )

    # ------------------------------------------------------------------------
    # Ring errors
    # ------------------------------------------------------------------------

    if response.status_code not in (200, 206):

        print(
            "[HISTORY VIDEO] Ring error response:",
            response.text[:3000],
        )

        return JsonResponse(
            {
                "error": "ring_video_api_error",
                "status_code": response.status_code,
                "details": response.text[:3000],
            },
            status=response.status_code,
        )

    # ------------------------------------------------------------------------
    # Return MP4 directly to browser
    # ------------------------------------------------------------------------

    content_type = (
        response.headers.get(
            "Content-Type"
        )
        or "video/mp4"
    )

    django_response = HttpResponse(
        response.content,
        content_type=content_type,
        status=response.status_code,
    )

    # Tell browser this is playable media.
    django_response["Accept-Ranges"] = "bytes"

    # Preserve useful Ring media metadata.
    for header_name in (
        "Content-Length",
        "Content-Range",
        "X-Media-Length",
        "X-Media-Duration",
        "X-Request-ID",
    ):

        value = response.headers.get(
            header_name
        )

        if value:
            django_response[header_name] = value

    print(
        "[HISTORY VIDEO] Returning",
        len(response.content),
        "bytes to browser",
    )

    print("=" * 70)

    return django_response
