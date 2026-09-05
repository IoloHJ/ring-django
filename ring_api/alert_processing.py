from datetime import datetime, timezone

from .models import RingAlert


def create_alert_from_payload(payload):
    """Create the local alert represented by a Ring webhook payload."""
    payload = payload or {}
    data = payload.get("data") or {}
    attributes = data.get("attributes") or {}
    event_id = data.get("id")

    if not event_id:
        return None, False

    event_type = data.get("type", "unknown")
    sub_type = attributes.get("sub_type", "")
    device_id = attributes.get("source", "")

    if event_type == "motion_detected":
        message = {
            "human": "Person detected",
            "vehicle": "Vehicle detected",
            "other_motion": "Motion detected",
        }.get(sub_type, "Motion detected")
    else:
        message = event_type.replace("_", " ").capitalize()

    timestamp = None
    timestamp_ms = attributes.get("timestamp")

    if timestamp_ms:
        try:
            timestamp = datetime.fromtimestamp(
                int(timestamp_ms) / 1000,
                tz=timezone.utc,
            )
        except (TypeError, ValueError, OverflowError):
            timestamp = None

    return RingAlert.objects.get_or_create(
        event_id=str(event_id),
        defaults={
            "device_id": str(device_id or ""),
            "device_name": "Unknown Device",
            "event_type": event_type,
            "message": message,
            "timestamp": timestamp,
            "payload": payload,
        },
    )


def create_alert_from_history_event(event, device_id, device_name="Unknown Device"):
    """Create a local alert from Ring history metadata, without media."""
    event = event or {}
    attributes = event.get("attributes") or {}
    event_id = event.get("id")

    if not event_id:
        return None, False

    event_type = (
        attributes.get("event_type")
        or attributes.get("type")
        or event.get("type")
        or "unknown"
    )
    event_type = str(event_type)
    message = (
        "Motion detected"
        if "motion" in event_type.lower()
        else event_type.replace("_", " ").capitalize()
    )

    timestamp = parse_ring_timestamp(
        attributes.get("start")
    )

    return RingAlert.objects.get_or_create(
        event_id=str(event_id),
        defaults={
            "device_id": str(device_id or ""),
            "device_name": str(device_name or "Unknown Device"),
            "event_type": event_type,
            "message": message,
            "timestamp": timestamp,
            "payload": {"source": "history", "event": event},
        },
    )


def parse_ring_timestamp(value):
    if value in (None, ""):
        return None

    try:
        numeric = float(value)
        if abs(numeric) < 100000000000:
            numeric *= 1000
        return datetime.fromtimestamp(
            numeric / 1000,
            tz=timezone.utc,
        )
    except (TypeError, ValueError, OverflowError):
        pass

    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except ValueError:
        return None
