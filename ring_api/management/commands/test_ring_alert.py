import uuid
import random

import requests

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ring_api.models import RingAlert, RingToken


class Command(BaseCommand):
    help = "Generate a fake alert to test the Alerts page polling and live trigger."

    def add_arguments(self, parser):

        parser.add_argument(
            "--device-id",
            help="Ring device ID. If omitted, choose a random online camera.",
        )

        parser.add_argument(
            "--device-name",
            default="Test Ring Camera",
            help="Name to display for the test camera.",
        )

        parser.add_argument(
            "--event-type",
            default="motion",
            help="Alert event type.",
        )

    def handle(self, *args, **options):

        device_id = options["device_id"]
        device_name = options["device_name"]
        event_type = options["event_type"]

        if not device_id:
            device_id, device_name = self.random_online_device()

        now = timezone.now()

        event_id = (
            "TEST-"
            + uuid.uuid4().hex.upper()
        )

        alert = RingAlert.objects.create(

            event_id=event_id,

            device_id=str(
                device_id
            ),

            device_name=device_name,

            event_type=event_type,

            message=(
                "TEST ALERT — "
                "This is a simulated Ring alert."
            ),

            timestamp=now,

            created_at=now,

            read=False,
        )

        self.stdout.write("")

        self.stdout.write(
            self.style.SUCCESS(
                "=========================================="
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                "       TEST RING ALERT CREATED"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                "=========================================="
            )
        )

        self.stdout.write(
            f"Alert ID:    {alert.id}"
        )

        self.stdout.write(
            f"Event ID:    {alert.event_id}"
        )

        self.stdout.write(
            f"Device ID:   {alert.device_id}"
        )

        self.stdout.write(
            f"Device Name: {alert.device_name}"
        )

        self.stdout.write(
            f"Event Type:  {alert.event_type}"
        )

        self.stdout.write(
            f"Timestamp:   {alert.timestamp}"
        )

        self.stdout.write(
            ""
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Alert is now available through:"
            )
        )

        self.stdout.write(
            "/ring/alerts/api/"
        )

        self.stdout.write(
            ""
        )

        self.stdout.write(
            self.style.WARNING(
                "Keep the Alerts page open to see it appear in the list."
            )
        )

        self.stdout.write(
            self.style.WARNING(
                "A genuinely new test alert will stop playback"
            )
        )

        self.stdout.write(
            self.style.WARNING(
                "and start live using the selected device ID."
            )
        )

        self.stdout.write("")

    def random_online_device(self):
        token = RingToken.objects.order_by("-updated_at").first()

        if not token or not token.access_token:
            raise CommandError(
                "No Ring access token is available to find an online camera."
            )

        base_url = settings.RING_API_BASE.rstrip("/")
        headers = {
            "Authorization": f"Bearer {token.access_token}",
            "Accept": "application/vnd.api+json",
        }

        try:
            response = requests.get(
                f"{base_url}/v1/devices",
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            devices = response.json().get("data", [])
        except (requests.RequestException, ValueError) as exc:
            raise CommandError(
                f"Unable to load Ring devices: {exc}"
            ) from exc

        online_devices = []

        for device in devices:
            device_id = device.get("id")

            if not device_id or not self.device_is_online(
                base_url,
                headers,
                device_id,
            ):
                continue

            attributes = device.get("attributes") or {}
            device_name = (
                attributes.get("description")
                or attributes.get("name")
                or attributes.get("device_name")
                or "Ring Camera"
            )
            online_devices.append((str(device_id), device_name))

        if not online_devices:
            raise CommandError("No online Ring cameras were found.")

        return random.choice(online_devices)

    def device_is_online(self, base_url, headers, device_id):
        try:
            response = requests.get(
                f"{base_url}/v1/devices/{device_id}/status",
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            return self.status_payload_is_online(response.json())
        except (requests.RequestException, ValueError):
            return False

    def status_payload_is_online(self, payload):
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key in {
                    "online",
                    "is_online",
                    "connection_status",
                    "connectionState",
                    "status",
                }:
                    if value is True:
                        return True
                    if str(value).lower() in {"online", "connected"}:
                        return True

                if self.status_payload_is_online(value):
                    return True

        elif isinstance(payload, list):
            return any(
                self.status_payload_is_online(item)
                for item in payload
            )

        return False
