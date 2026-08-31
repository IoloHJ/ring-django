from django.urls import path

from . import views


urlpatterns = [

    # --------------------------------------------------------
    # RING AUTH
    # --------------------------------------------------------

    path(
        "ring/token/",
        views.ring_token,
        name="ring-token",
    ),

    path(
        "ring/link/",
        views.ring_link,
        name="ring-link",
    ),

    path(
        "ring/callback/",
        views.ring_callback,
        name="ring-callback",
    ),

    # --------------------------------------------------------
    # RING DEVICES
    # --------------------------------------------------------

    path(
        "ring/devices/",
        views.ring_devices,
        name="ring-devices",
    ),

    # --------------------------------------------------------
    # LIVE VIEW PAGE
    # --------------------------------------------------------

    path(
        "ring/live/",
        views.ring_live_page,
        name="ring-live",
    ),

    # --------------------------------------------------------
    # LIVE WHEP
    # --------------------------------------------------------

    path(
        "ring/live/<path:device_id>/start/",
        views.ring_live_start,
        name="ring-live-start",
    ),

    path(
        "ring/live/<path:device_id>/stop/",
        views.ring_live_stop,
        name="ring-live-stop",
    ),

    # --------------------------------------------------------
    # WEBHOOK
    # --------------------------------------------------------

    path(
        "ring/webhook/",
        views.ring_webhook,
        name="ring-webhook",
    ),

    # --------------------------------------------------------
    # USER
    # --------------------------------------------------------

    path(
        "user/",
        views.ring_user,
        name="ring-user",
    ),
]