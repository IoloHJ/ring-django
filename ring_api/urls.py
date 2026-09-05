from django.urls import path

from . import views, alerts_views


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

    # ============================================================
    path(
        "ring/history/",
        views.ring_history,
        name="ring-history",
    ),

    # ============================================================
    # RING HISTORY VIDEO
    #
    # IMPORTANT:
    # This specific route must be before the generic
    # history/<device_id>/ route.
    # ============================================================

    path(
        "ring/history/<str:device_id>/video/<str:event_id>/",
        views.ring_history_video,
        name="ring-history-video",
    ),

    # ============================================================
    # RING HISTORY API
    # ============================================================

    path(
        "ring/history/<str:device_id>/",
        views.ring_history_api,
        name="ring-history-api",
    ),

    path(
        "ring/alerts/",
        alerts_views.ring_alerts_page,
        name="ring_alerts",
    ),

    # ============================================================
    # ALERTS API
    # ============================================================

    path(
        "ring/alerts/api/",
        alerts_views.ring_alerts_api,
        name="ring_alerts_api",
    ),

    path(
        "ring/alerts/<int:alert_id>/video/",
        alerts_views.ring_alert_video,
        name="ring_alert_video",
    ),

    # ============================================================
    # SINGLE ALERT
    # ============================================================

    path(
        "ring/alerts/<int:alert_id>/",
        alerts_views.ring_alert_detail,
        name="ring_alert_detail",
    ),

    # ============================================================
    # ALERT LIVE FEED
    # ============================================================

    path(
        "ring/alerts/<str:device_id>/live/start/",
        alerts_views.ring_alert_live_start,
        name="ring_alert_live_start",
    ),

    path(
        "ring/alerts/<str:device_id>/live/stop/",
        alerts_views.ring_alert_live_stop,
        name="ring_alert_live_stop",
    ),
]
