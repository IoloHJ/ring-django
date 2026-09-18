from django.conf import settings
from django.shortcuts import redirect


PUBLIC_PREFIXES = (
    "/security/",
    "/admin/",
    "/static/",
    "/ring/webhook/",
    "/ring/link/",
    "/ring/callback/",
    "/ring/token/",
    "/ring/mobile/install/",
    "/ring/mobile/android/",
    "/ring/mobile/ios/",
)


class SecurityLoginRedirectMiddleware:
    """Send unauthenticated browser page requests to the security login."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._needs_login(request):
            next_url = request.get_full_path()
            return redirect(f"{settings.LOGIN_URL}?next={next_url}")
        return self.get_response(request)

    @staticmethod
    def _needs_login(request):
        if getattr(request, "user", None) and request.user.is_authenticated:
            return False
        if request.path.startswith(PUBLIC_PREFIXES):
            return False
        if request.headers.get("Authorization", "").startswith("Bearer "):
            return False
        if request.method != "GET":
            return False
        accepted = request.headers.get("Accept", "")
        return "text/html" in accepted or not accepted
