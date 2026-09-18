import io
import json
import logging

import pyotp
import qrcode
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from .models import AppInstallation, SecurityProfile
from .services import app_installation_from_request, create_app_installation


logger = logging.getLogger(__name__)


def profile_for(user):
    profile, _ = SecurityProfile.objects.get_or_create(user=user)
    return profile


def pending_user(request):
    user_id = request.session.get("security_2fa_user_id")
    if not user_id:
        return None
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(id=user_id, is_active=True).first()


def security_login(request):
    if request.user.is_authenticated:
        return redirect("security-2fa-setup" if not profile_for(request.user).totp_enabled else "ring_alerts")

    error = None
    if request.method == "POST":
        user = authenticate(
            request,
            username=request.POST.get("username", "").strip(),
            password=request.POST.get("password", ""),
        )
        if user is None:
            error = "Invalid username or password."
        else:
            request.session["security_2fa_user_id"] = user.id
            request.session["security_next"] = request.POST.get("next", "")
            if profile_for(user).totp_enabled:
                return redirect("security-2fa-verify")
            return redirect("security-2fa-setup")

    return render(
        request,
        "security/login.html",
        {"error": error, "next_url": request.POST.get("next", request.GET.get("next", ""))},
    )


@login_required
def security_2fa_setup(request):
    profile = profile_for(request.user)
    if not profile.totp_secret:
        profile.totp_secret = pyotp.random_base32()
        profile.save(update_fields=["totp_secret", "updated_at"])
    return render(
        request,
        "security/2fa_setup.html",
        {"secret": profile.totp_secret, "username": request.user.username},
    )


def security_2fa_setup_pending(request):
    user = pending_user(request)
    if not user:
        return redirect("security-login")
    profile = profile_for(user)
    if not profile.totp_secret:
        profile.totp_secret = pyotp.random_base32()
        profile.save(update_fields=["totp_secret", "updated_at"])
    return render(
        request,
        "security/2fa_setup.html",
        {"secret": profile.totp_secret, "username": user.username, "pending": True},
    )


def security_2fa_qr(request):
    user = request.user if request.user.is_authenticated else pending_user(request)
    if not user:
        return HttpResponse(status=403)
    profile = profile_for(user)
    if not profile.totp_secret:
        return HttpResponse(status=404)
    uri = pyotp.TOTP(profile.totp_secret).provisioning_uri(
        name=user.username,
        issuer_name="Ring Security",
    )
    image = qrcode.make(uri)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return HttpResponse(output.getvalue(), content_type="image/png")


@require_http_methods(["GET", "POST"])
def security_2fa_verify(request):
    user = pending_user(request)
    if not user and request.user.is_authenticated:
        user = request.user
    if not user:
        return redirect("security-login")

    error = None
    if request.method == "POST":
        profile = profile_for(user)
        code = request.POST.get("code", "").replace(" ", "")
        if profile.totp_secret and pyotp.TOTP(profile.totp_secret).verify(code, valid_window=1):
            profile.totp_enabled = True
            profile.save(update_fields=["totp_enabled", "updated_at"])
            login(request, user)
            next_url = request.session.pop("security_next", "")
            request.session.pop("security_2fa_user_id", None)
            return redirect(next_url or "ring_alerts")
        error = "That authenticator code is not valid."
    return render(request, "security/2fa_verify.html", {"error": error})


@require_POST
def security_logout(request):
    logout(request)
    return redirect("security-login")


@csrf_exempt
@require_POST
def security_app_activate(request):
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "invalid_json"}, status=400)

    user = authenticate(
        request,
        username=str(body.get("username", "")).strip(),
        password=str(body.get("password", "")),
    )
    if not user:
        return JsonResponse({"error": "invalid_credentials"}, status=401)
    profile = profile_for(user)
    if not profile.totp_enabled:
        return JsonResponse({"error": "two_factor_setup_required"}, status=403)
    code = str(body.get("code", "")).replace(" ", "")
    if not pyotp.TOTP(profile.totp_secret).verify(code, valid_window=1):
        return JsonResponse({"error": "invalid_two_factor_code"}, status=401)

    installation_id = str(body.get("installation_id", "")).strip()
    platform = str(body.get("platform", "")).strip()
    if not installation_id or not platform:
        return JsonResponse({"error": "installation_id_and_platform_required"}, status=400)
    installation, token = create_app_installation(
        user,
        installation_id,
        platform,
        str(body.get("app_version", "")),
    )
    return JsonResponse({
        "activated": True,
        "token": token,
        "installation_id": installation.installation_id,
        "user": user.username,
    })


@csrf_exempt
@require_POST
def security_app_deactivate(request):
    installation = app_installation_from_request(request)
    if not installation:
        return JsonResponse({"error": "invalid_app_token"}, status=401)
    installation.deactivated_at = timezone.now()
    installation.save(update_fields=["deactivated_at", "last_seen_at"])
    return JsonResponse({"deactivated": True})
