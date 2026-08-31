import base64
import hashlib
import hmac
import logging
import os
import time

import requests

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

logger = logging.getLogger(__name__)


# ============================================================
# CONFIG
# ============================================================

RING_TOKEN_URL = os.getenv(
    "RING_TOKEN_URL",
    "https://oauth.ring.com/oauth/token",
)

RING_API_BASE = os.getenv(
    "RING_API_BASE",
    "https://api.amazonvision.com",
)

RING_CLIENT_ID = os.getenv("RING_CLIENT_ID", "")
RING_CLIENT_SECRET = os.getenv("RING_CLIENT_SECRET", "")

RING_HMAC_SIGNING_KEY = os.getenv(
    "RING_HMAC_SIGNING_KEY",
    "",
)

RING_TOKEN_TTL = 60 * 60 * 24 * 30

RING_NONCE_MAX_AGE = 600


# ============================================================
# HELPERS
# ============================================================

def ring_api_headers(access_token):
    """
    Headers used for Amazon Vision / Ring API requests.
    """
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def compute_ring_nonce(time_param, account_id):
    """
    Ring nonce:

        HMAC-SHA256(
            HMAC signing key,
            "{timestamp_ms}:{account_id}"
        )

    Output:
        URL-safe Base64 without '=' padding.
    """

    if not RING_HMAC_SIGNING_KEY:
        raise RuntimeError(
            "RING_HMAC_SIGNING_KEY is not configured"
        )

    payload = f"{time_param}:{account_id}"

    digest = hmac.new(
        RING_HMAC_SIGNING_KEY.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    return (
        base64.urlsafe_b64encode(digest)
        .rstrip(b"=")
        .decode("utf-8")
    )


def validate_ring_timestamp(time_param):
    """
    Ring sends the timestamp in milliseconds.

    Reject anything older/newer than the configured
    10-minute window.
    """

    try:
        timestamp_ms = int(time_param)
    except (TypeError, ValueError):
        return False

    now_ms = int(time.time() * 1000)

    difference_ms = abs(now_ms - timestamp_ms)

    return difference_ms <= (
        RING_NONCE_MAX_AGE * 1000
    )


def mask_email(email):
    """
    Turn:

        example@example.com

    into:

        e******e@example.com

    Ring expects an obfuscated partner account identifier.
    """

    if not email:
        return ""

    if "@" not in email:
        return email[:1] + "***"

    local, domain = email.split("@", 1)

    if len(local) <= 2:
        masked_local = local[:1] + "***"
    else:
        masked_local = (
            local[0]
            + "***"
            + local[-1]
        )

    return f"{masked_local}@{domain}"


def token_cache_key(account_id):
    """
    Cache key for an unclaimed Ring token.
    """

    return f"ring:unclaimed:{account_id}"


def get_unclaimed_tokens():
    """
    Retrieve currently unclaimed Ring token records.

    For the first implementation we're using Django cache.

    Later we should move this to a database model so tokens
    survive cache/container restarts.
    """

    accounts = cache.get("ring:unclaimed:accounts", [])

    records = []

    for account_id in accounts:

        record = cache.get(
            token_cache_key(account_id)
        )

        if record:
            records.append(record)

    return records


def save_unclaimed_token(record):
    """
    Store a token as unclaimed.
    """

    account_id = record["account_id"]

    cache.set(
        token_cache_key(account_id),
        record,
        RING_TOKEN_TTL,
    )

    accounts = cache.get(
        "ring:unclaimed:accounts",
        [],
    )

    if account_id not in accounts:
        accounts.append(account_id)

    cache.set(
        "ring:unclaimed:accounts",
        accounts,
        RING_TOKEN_TTL,
    )


def remove_unclaimed_token(account_id):
    """
    Remove token after it has been claimed.
    """

    cache.delete(
        token_cache_key(account_id)
    )

    accounts = cache.get(
        "ring:unclaimed:accounts",
        [],
    )

    if account_id in accounts:
        accounts.remove(account_id)

    cache.set(
        "ring:unclaimed:accounts",
        accounts,
        RING_TOKEN_TTL,
    )


# ============================================================
# 1. RING TOKEN EXCHANGE
# ============================================================

@csrf_exempt
@require_POST
def ring_token(request):
    """
    Ring calls this endpoint server-to-server.

    POST /ring/token/

    Ring sends:

        code
        client_id

    We exchange the authorization code for:

        access_token
        refresh_token

    Then call:

        GET /v1/users/me

    to obtain the Ring Account ID.

    The token is initially stored as UNCLAIMED because
    we don't yet know which Django user is linking it.
    """

    logger.info(
        "Ring token exchange request received"
    )

    logger.info(
        "Ring token exchange content type: %s",
        request.content_type,
    )

    code = request.POST.get("code")
    client_id = request.POST.get("client_id")

    if not code:
        logger.error(
            "Ring token exchange missing code"
        )

        return JsonResponse(
            {
                "error": "missing_code"
            },
            status=400,
        )

    if not client_id:
        logger.error(
            "Ring token exchange missing client_id"
        )

        return JsonResponse(
            {
                "error": "missing_client_id"
            },
            status=400,
        )

    if not RING_CLIENT_ID:
        logger.error(
            "RING_CLIENT_ID is not configured"
        )

        return JsonResponse(
            {
                "error": "server_configuration_error"
            },
            status=500,
        )

    if not RING_CLIENT_SECRET:
        logger.error(
            "RING_CLIENT_SECRET is not configured"
        )

        return JsonResponse(
            {
                "error": "server_configuration_error"
            },
            status=500,
        )

    # --------------------------------------------------------
    # Verify client ID
    # --------------------------------------------------------

    if not hmac.compare_digest(
        client_id,
        RING_CLIENT_ID,
    ):
        logger.error(
            "Ring supplied an unexpected client_id"
        )

        return JsonResponse(
            {
                "error": "invalid_client"
            },
            status=401,
        )

    # --------------------------------------------------------
    # Exchange authorization code
    # --------------------------------------------------------

    token_data = {
        "grant_type": "authorization_code",
        "client_id": RING_CLIENT_ID,
        "client_secret": RING_CLIENT_SECRET,
        "code": code,
    }

    logger.info(
        "Exchanging Ring authorization code"
    )

    try:

        response = requests.post(
            RING_TOKEN_URL,
            data=token_data,
            headers={
                "Content-Type":
                    "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=20,
        )

    except requests.RequestException:
        logger.exception(
            "Unable to contact Ring OAuth server"
        )

        return JsonResponse(
            {
                "error": "ring_oauth_unavailable"
            },
            status=502,
        )

    # --------------------------------------------------------
    # Don't log token response
    # --------------------------------------------------------

    if response.status_code != 200:

        logger.error(
            "Ring token exchange failed: HTTP %s",
            response.status_code,
        )

        try:
            error_body = response.json()

            # Log only safe OAuth error fields.
            logger.error(
                "Ring OAuth error: %s",
                {
                    key: value
                    for key, value in error_body.items()
                    if key in (
                        "error",
                        "error_description",
                    )
                },
            )

        except ValueError:
            logger.error(
                "Ring OAuth returned non-JSON error"
            )

        return JsonResponse(
            {
                "error": "token_exchange_failed"
            },
            status=502,
        )

    try:
        tokens = response.json()

    except ValueError:
        logger.error(
            "Ring OAuth returned invalid JSON"
        )

        return JsonResponse(
            {
                "error": "invalid_ring_response"
            },
            status=502,
        )

    access_token = tokens.get(
        "access_token"
    )

    refresh_token = tokens.get(
        "refresh_token"
    )

    expires_in = tokens.get(
        "expires_in",
        14400,
    )

    if not access_token:
        logger.error(
            "Ring OAuth response did not contain access_token"
        )

        return JsonResponse(
            {
                "error": "missing_access_token"
            },
            status=502,
        )

    if not refresh_token:
        logger.error(
            "Ring OAuth response did not contain refresh_token"
        )

        return JsonResponse(
            {
                "error": "missing_refresh_token"
            },
            status=502,
        )

    # --------------------------------------------------------
    # Get Ring Account ID
    # --------------------------------------------------------

    logger.info(
        "Retrieving Ring Account ID"
    )

    try:

        user_response = requests.get(
            f"{RING_API_BASE}/v1/users/me",
            headers=ring_api_headers(
                access_token
            ),
            timeout=20,
        )

    except requests.RequestException:
        logger.exception(
            "Unable to retrieve Ring Account ID"
        )

        return JsonResponse(
            {
                "error": "ring_user_lookup_failed"
            },
            status=502,
        )

    if user_response.status_code != 200:

        logger.error(
            "Ring /v1/users/me returned HTTP %s",
            user_response.status_code,
        )

        return JsonResponse(
            {
                "error": "ring_user_lookup_failed"
            },
            status=502,
        )

    try:

        user_data = user_response.json()

    except ValueError:

        logger.error(
            "Invalid JSON from Ring /v1/users/me"
        )

        return JsonResponse(
            {
                "error": "invalid_ring_user_response"
            },
            status=502,
        )

    # JSON:API response:
    #
    # {
    #   "data": {
    #       "id": "ava1.ring.account...."
    #   }
    # }

    account_id = (
        user_data
        .get("data", {})
        .get("id")
    )

    if not account_id:

        logger.error(
            "Ring /v1/users/me did not return Account ID"
        )

        return JsonResponse(
            {
                "error": "missing_ring_account_id"
            },
            status=502,
        )

    # --------------------------------------------------------
    # Store as UNCLAIMED
    # --------------------------------------------------------

    record = {
        "account_id": account_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
        "received_at": int(time.time()),
    }

    save_unclaimed_token(record)

    logger.info(
        "Ring token stored as unclaimed for Account ID %s",
        account_id,
    )

    # IMPORTANT:
    #
    # Never return the access/refresh tokens to Ring or
    # write them to the response.
    #
    # Ring only needs a successful response here.

    return JsonResponse(
        {
            "status": "ok",
        },
        status=200,
    )


# ============================================================
# 2. RING ACCOUNT LINK
# ============================================================

@login_required
@require_GET
def ring_link(request):
    """
    Ring redirects the browser here:

        /ring/link/?nonce=...&time=...

    The user MUST be authenticated to our Django application.

    We save nonce/time into the Django session and then try
    to match it against the unclaimed Ring token pool.
    """

    logger.info(
        "Ring account-link request received"
    )

    nonce = request.GET.get("nonce")
    time_param = request.GET.get("time")

    if not nonce or not time_param:

        logger.warning(
            "Ring link request missing nonce or time"
        )

        return JsonResponse(
            {
                "error": "missing_nonce_or_time"
            },
            status=400,
        )

    # --------------------------------------------------------
    # Validate timestamp
    # --------------------------------------------------------

    if not validate_ring_timestamp(
        time_param
    ):

        logger.warning(
            "Ring link timestamp outside validation window"
        )

        return JsonResponse(
            {
                "error": "expired_link"
            },
            status=400,
        )

    # --------------------------------------------------------
    # Store link attempt in session
    # --------------------------------------------------------

    request.session["ring_nonce"] = nonce
    request.session["ring_nonce_time"] = time_param

    request.session.modified = True

    # --------------------------------------------------------
    # Find matching unclaimed token
    # --------------------------------------------------------

    matching_record = None

    for record in get_unclaimed_tokens():

        account_id = record.get(
            "account_id"
        )

        if not account_id:
            continue

        try:

            expected_nonce = compute_ring_nonce(
                time_param,
                account_id,
            )

        except RuntimeError:
            logger.exception(
                "Ring HMAC signing key is not configured"
            )

            return JsonResponse(
                {
                    "error":
                        "server_configuration_error"
                },
                status=500,
            )

        if hmac.compare_digest(
            expected_nonce,
            nonce,
        ):

            matching_record = record
            break

    if not matching_record:

        logger.warning(
            "No matching unclaimed Ring token found"
        )

        return JsonResponse(
            {
                "status": "waiting",
                "message":
                    "No matching Ring authorization was found.",
            },
            status=404,
        )

    # --------------------------------------------------------
    # We have found the Ring account
    # --------------------------------------------------------

    account_id = matching_record[
        "account_id"
    ]

    access_token = matching_record[
        "access_token"
    ]

    # --------------------------------------------------------
    # Partner account identifier
    # --------------------------------------------------------

    # Because @login_required is being used, this is the
    # authenticated Django user.

    user = request.user

    partner_identifier = mask_email(
        getattr(
            user,
            "email",
            "",
        )
    )

    if not partner_identifier:

        logger.error(
            "Authenticated Django user has no email"
        )

        return JsonResponse(
            {
                "error":
                    "authenticated_user_email_required"
            },
            status=400,
        )

    # --------------------------------------------------------
    # POST App Integrations
    # --------------------------------------------------------

    logger.info(
        "Confirming Ring account link for Account ID %s",
        account_id,
    )

    try:

        post_response = requests.post(
            f"{RING_API_BASE}/v1/accounts/me/app-integrations",
            headers=ring_api_headers(
                access_token
            ),
            json={
                "account_identifier":
                    partner_identifier,
                "nonce":
                    nonce,
            },
            timeout=20,
        )

    except requests.RequestException:

        logger.exception(
            "Ring App Integrations POST failed"
        )

        return JsonResponse(
            {
                "error":
                    "ring_account_link_failed"
            },
            status=502,
        )

    if post_response.status_code != 200:

        logger.error(
            "Ring App Integrations POST returned HTTP %s",
            post_response.status_code,
        )

        try:
            logger.error(
                "Ring response: %s",
                post_response.json(),
            )

        except ValueError:
            pass

        return JsonResponse(
            {
                "error":
                    "ring_nonce_verification_failed"
            },
            status=502,
        )

    # --------------------------------------------------------
    # PATCH App Integrations -> completed
    # --------------------------------------------------------

    logger.info(
        "Completing Ring account integration"
    )

    try:

        patch_response = requests.patch(
            f"{RING_API_BASE}/v1/accounts/me/app-integrations",
            headers=ring_api_headers(
                access_token
            ),
            json={
                "status":
                    "completed",
                "account_identifier":
                    partner_identifier,
            },
            timeout=20,
        )

    except requests.RequestException:

        logger.exception(
            "Ring App Integrations PATCH failed"
        )

        return JsonResponse(
            {
                "error":
                    "ring_account_completion_failed"
            },
            status=502,
        )

    if patch_response.status_code != 200:

        logger.error(
            "Ring App Integrations PATCH returned HTTP %s",
            patch_response.status_code,
        )

        try:
            logger.error(
                "Ring response: %s",
                patch_response.json(),
            )

        except ValueError:
            pass

        return JsonResponse(
            {
                "error":
                    "ring_account_completion_failed"
            },
            status=502,
        )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # At this point the Ring account is successfully linked.
    #
    # Remove the token from the unclaimed pool.
    # --------------------------------------------------------

    remove_unclaimed_token(
        account_id
    )

    # Store useful non-secret information in session.

    request.session[
        "ring_account_id"
    ] = account_id

    request.session[
        "ring_linked"
    ] = True

    request.session.modified = True

    logger.info(
        "Ring account successfully linked: %s",
        account_id,
    )

    return JsonResponse(
        {
            "status": "completed",
            "message":
                "Ring account linked successfully.",
            "account_id":
                account_id,
        },
        status=200,
    )