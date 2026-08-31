import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ring_api.models import RingAlert


class Command(BaseCommand):
    help = "Generate a fake Ring alert for testing the Alerts live-feed system."

    def add_arguments(self, parser):

        parser.add_argument(
            "--device-id",
            required=True,
            help="Real Ring device ID to associate with the test alert.",
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
                "This creates a database alert only."
            )
        )

        self.stdout.write(
            self.style.WARNING(
                "The live feed will use the real device ID"
            )
        )

        self.stdout.write(
            self.style.WARNING(
                "when the Alerts page starts its WHEP session."
            )
        )

        self.stdout.write("")