from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.utils import timezone
from django.core.management import call_command

from ring_api.alert_processing import create_alert_from_history_event
from ring_api.models import RingAlert, RingToken


@override_settings(MIDDLEWARE=[])
class RingWebhookTests(TestCase):
    def test_webhook_creates_alert_for_alerts_page(self):
        response = self.client.post(
            "/ring/webhook/",
            data={
                "data": {
                    "id": "event-123",
                    "type": "motion_detected",
                    "attributes": {
                        "source": "device-456",
                        "sub_type": "human",
                        "timestamp": 1725000000000,
                    },
                },
            },
            content_type="application/json",
            HTTP_X_REQUEST_ID="request-123",
        )

        self.assertEqual(response.status_code, 200)
        alert = RingAlert.objects.get(event_id="event-123")
        self.assertEqual(alert.device_id, "device-456")
        self.assertEqual(alert.message, "Person detected")

    def test_alert_api_returns_persisted_webhook_alert(self):
        self.client.post(
            "/ring/webhook/",
            data={
                "data": {
                    "id": "event-789",
                    "type": "motion_detected",
                    "attributes": {"source": "device-999"},
                },
            },
            content_type="application/json",
            HTTP_X_REQUEST_ID="request-789",
        )

        response = self.client.get("/ring/alerts/api/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["alerts"][0]["device_id"], "device-999")

    def test_history_event_creates_alert_metadata_without_video(self):
        alert, created = create_alert_from_history_event(
            {
                "id": "history-123",
                "type": "motion",
                "attributes": {"start": "2026-09-04T12:00:00Z"},
            },
            "device-history",
            "Front Door",
        )

        self.assertTrue(created)
        self.assertEqual(alert.device_id, "device-history")
        self.assertEqual(alert.device_name, "Front Door")
        self.assertEqual(alert.payload["source"], "history")

    def test_alert_api_orders_by_event_timestamp(self):
        now = timezone.now()
        RingAlert.objects.create(
            event_id="older",
            device_id="device-1",
            timestamp=now - timedelta(minutes=5),
        )
        RingAlert.objects.create(
            event_id="newer",
            device_id="device-1",
            timestamp=now,
        )

        response = self.client.get("/ring/alerts/api/")

        self.assertEqual(response.json()["alerts"][0]["event_id"], "newer")

    @patch("ring_api.alerts_views.requests.get")
    def test_alert_api_fills_unknown_device_name(self, get):
        RingToken.objects.create(
            account_id="account-device-name",
            access_token="token",
            refresh_token="refresh",
        )
        alert = RingAlert.objects.create(
            event_id="unknown-device-name",
            device_id="device-named",
            device_name="Unknown Device",
            timestamp=timezone.now(),
        )
        get.return_value = Mock(
            status_code=200,
            headers={},
        )
        get.return_value.json.return_value = {
            "data": [
                {
                    "id": "device-named",
                    "attributes": {"description": "Front Door"},
                }
            ]
        }

        response = self.client.get("/ring/alerts/api/")

        self.assertEqual(response.json()["alerts"][0]["device_name"], "Front Door")
        alert.refresh_from_db()
        self.assertEqual(alert.device_name, "Front Door")

    def test_test_alert_command_creates_alert_for_polling(self):
        call_command(
            "test_ring_alert",
            device_id="device-test",
        )

        response = self.client.get("/ring/alerts/api/")
        alert = response.json()["alerts"][0]

        self.assertEqual(alert["device_id"], "device-test")
        self.assertTrue(alert["event_id"].startswith("TEST-"))

    @patch("ring_api.alerts_views.requests.post")
    def test_alert_video_uses_alert_timestamp_and_device(self, post):
        RingToken.objects.create(
            account_id="account-1",
            access_token="token",
            refresh_token="refresh",
        )
        alert = RingAlert.objects.create(
            event_id="video-event",
            device_id="device-video",
            timestamp=timezone.now(),
        )
        post.return_value = Mock(
            status_code=200,
            content=b"video",
            text="",
            headers={"Content-Type": "video/mp4"},
        )

        response = self.client.get(
            f"/ring/alerts/{alert.id}/video/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"video")
        request = post.call_args
        self.assertIn(
            "/v1/devices/device-video/media/video/download",
            request.args[0],
        )
        self.assertEqual(request.kwargs["json"]["duration"], 60000)
