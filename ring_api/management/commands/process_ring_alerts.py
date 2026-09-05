import requests

from django.conf import settings
from django.core.management.base import BaseCommand

from ring_api.alert_processing import (
    create_alert_from_history_event,
    create_alert_from_payload,
)
from ring_api.models import RingAlert, RingToken, RingWebhookEvent


class Command(BaseCommand):
    help = "Process webhook events and optionally backfill Ring history alerts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--backfill",
            action="store_true",
            help="Import alert metadata from Ring history; no videos are downloaded.",
        )
        parser.add_argument(
            "--device-id",
            help="Backfill only this Ring device when --backfill is used.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum history events to import per device (default: 100).",
        )

    def handle(self, *args, **options):

        events = (
            RingWebhookEvent.objects
            .order_by("id")
        )

        created = 0
        skipped = 0

        for event in events:

            payload = event.payload or {}

            # ========================================================
            # RING PAYLOAD
            # ========================================================

            data = payload.get("data") or {}
            event_id = data.get("id")

            if not event_id:

                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping webhook {event.id}: "
                        "no event ID"
                    )
                )

                skipped += 1

                continue

            # ========================================================
            # CREATE ALERT
            # ========================================================

            alert, was_created = create_alert_from_payload(payload)

            if was_created:

                created += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created alert #{alert.id}: "
                        f"{alert.message} | "
                        f"{alert.device_id}"
                    )
                )

            else:

                self.stdout.write(
                    f"Already processed: {event_id}"
                )

        if options["backfill"]:
            created, skipped = self.backfill_history(
                options["device_id"],
                options["limit"],
                created,
                skipped,
            )

        # ============================================================
        # SUMMARY
        # ============================================================

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Finished. Created: {created} | "
                f"Skipped: {skipped}"
            )
        )

    def backfill_history(self, selected_device_id, limit, created, skipped):
        token = RingToken.objects.order_by("-updated_at").first()

        if not token or not token.access_token:
            self.stdout.write(
                self.style.ERROR("No Ring access token is available for backfill.")
            )
            return created, skipped

        base_url = settings.RING_API_BASE.rstrip("/")
        headers = {
            "Authorization": f"Bearer {token.access_token}",
            "Accept": "application/vnd.api+json",
        }

        try:
            response = requests.get(
                f"{base_url}/v1/devices",
                headers=headers,
                timeout=60,
            )
            response.raise_for_status()
            devices = response.json().get("data", [])
        except (requests.RequestException, ValueError) as exc:
            self.stdout.write(
                self.style.ERROR(f"Unable to load Ring devices: {exc}")
            )
            return created, skipped

        if selected_device_id:
            devices = [
                device for device in devices
                if str(device.get("id")) == str(selected_device_id)
            ]

        for device in devices:
            device_id = device.get("id")
            if not device_id:
                continue

            attributes = device.get("attributes") or {}
            device_name = (
                attributes.get("description")
                or attributes.get("name")
                or attributes.get("device_name")
                or "Unknown Device"
            )
            RingAlert.objects.filter(
                device_id=str(device_id),
                device_name="Unknown Device",
            ).update(device_name=device_name)
            events_url = (
                f"{base_url}/v1/history/devices/"
                f"{device_id}/events"
            )

            try:
                response = requests.get(
                    events_url,
                    headers=headers,
                    params={"page[limit]": limit},
                    timeout=60,
                )
                response.raise_for_status()
                events = response.json().get("data", [])
            except (requests.RequestException, ValueError) as exc:
                self.stdout.write(
                    self.style.WARNING(
                        f"Unable to load history for {device_id}: {exc}"
                    )
                )
                continue

            for event in events[:limit]:
                alert, was_created = create_alert_from_history_event(
                    event,
                    device_id,
                    device_name,
                )

                if not alert:
                    skipped += 1
                elif was_created:
                    created += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Backfilled alert #{alert.id}: "
                            f"{alert.message} | {alert.device_id}"
                        )
                    )

        return created, skipped
