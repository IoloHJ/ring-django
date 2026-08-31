from datetime import datetime, timezone

from django.core.management.base import BaseCommand

from ring_api.models import RingWebhookEvent, RingAlert


class Command(BaseCommand):
    help = "Process Ring webhook events into Ring alerts."

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
            attributes = data.get("attributes") or {}

            # ========================================================
            # EVENT ID
            # ========================================================

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
            # EVENT TYPE
            # ========================================================

            event_type = data.get(
                "type",
                "unknown",
            )

            # ========================================================
            # SUB TYPE
            #
            # Ring sends:
            #
            # human
            # vehicle
            # other_motion
            #
            # RingAlert doesn't currently have a sub_type column,
            # so we use it to determine the human-readable message.
            # The complete original value remains in payload.
            # ========================================================

            sub_type = attributes.get(
                "sub_type",
                "",
            )

            # ========================================================
            # DEVICE
            # ========================================================

            device_id = attributes.get(
                "source",
                "",
            )

            # ========================================================
            # MESSAGE
            # ========================================================

            if event_type == "motion_detected":

                if sub_type == "human":

                    message = "Person detected"

                elif sub_type == "vehicle":

                    message = "Vehicle detected"

                elif sub_type == "other_motion":

                    message = "Motion detected"

                else:

                    message = "Motion detected"

            else:

                message = (
                    event_type
                    .replace("_", " ")
                    .capitalize()
                )

            # ========================================================
            # TIMESTAMP
            # ========================================================

            timestamp = None

            timestamp_ms = attributes.get(
                "timestamp"
            )

            if timestamp_ms:

                try:

                    timestamp = datetime.fromtimestamp(
                        int(timestamp_ms) / 1000,
                        tz=timezone.utc,
                    )

                except (
                    TypeError,
                    ValueError,
                    OverflowError,
                ):

                    self.stdout.write(
                        self.style.WARNING(
                            f"Invalid timestamp for "
                            f"event {event_id}"
                        )
                    )

            # ========================================================
            # DEVICE NAME
            #
            # We'll populate this properly from Ring device
            # discovery once the basic alert pipeline is confirmed.
            # ========================================================

            device_name = "Unknown Device"

            # ========================================================
            # CREATE ALERT
            # ========================================================

            alert, was_created = (
                RingAlert.objects.get_or_create(
                    event_id=event_id,
                    defaults={
                        "device_id": device_id,
                        "device_name": device_name,
                        "event_type": event_type,
                        "message": message,
                        "timestamp": timestamp,
                        "payload": payload,
                    },
                )
            )

            if was_created:

                created += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created alert #{alert.id}: "
                        f"{message} | "
                        f"{sub_type or 'unknown'} | "
                        f"{device_id}"
                    )
                )

            else:

                self.stdout.write(
                    f"Already processed: {event_id}"
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