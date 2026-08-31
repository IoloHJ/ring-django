import os
from datetime import timedelta

import requests

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ring_api.models import RingToken


RING_TOKEN_URL = os.getenv(
    "RING_TOKEN_URL",
    "https://oauth.ring.com/oauth/token",
)


class Command(BaseCommand):
    help = "Refresh the stored Ring OAuth access token when it is expired or close to expiry."

    # Refresh this many seconds before the actual expiry.
    EXPIRY_BUFFER_SECONDS = 300

    def handle(self, *args, **options):
        self.stdout.write("[RING AUTH] Checking Ring token...")

        token = (
            RingToken.objects
            .order_by("-updated_at")
            .first()
        )

        if not token:
            raise CommandError(
                "No RingToken exists in the database."
            )

        if not token.refresh_token:
            raise CommandError(
                "RingToken exists but has no refresh_token."
            )

        # ------------------------------------------------------------
        # Work out whether the current access token is still valid
        # ------------------------------------------------------------

        now = timezone.now()

        if token.expires_in and token.created_at:
            expires_at = (
                token.created_at
                + timedelta(seconds=token.expires_in)
            )

            refresh_at = (
                expires_at
                - timedelta(
                    seconds=self.EXPIRY_BUFFER_SECONDS
                )
            )

            if now < refresh_at:
                remaining = expires_at - now

                self.stdout.write(
                    self.style.SUCCESS(
                        "[RING AUTH] Access token is still valid."
                    )
                )

                self.stdout.write(
                    f"[RING AUTH] Approximately "
                    f"{int(remaining.total_seconds())} seconds remaining."
                )

                return

        # ------------------------------------------------------------
        # Environment configuration
        # ------------------------------------------------------------

        client_id = os.getenv("RING_CLIENT_ID")
        client_secret = os.getenv("RING_CLIENT_SECRET")

        if not client_id:
            raise CommandError(
                "RING_CLIENT_ID is not configured."
            )

        if not client_secret:
            raise CommandError(
                "RING_CLIENT_SECRET is not configured."
            )

        # ------------------------------------------------------------
        # Refresh token
        # ------------------------------------------------------------

        self.stdout.write(
            "[RING AUTH] Access token expired or close to expiry."
        )

        self.stdout.write(
            "[RING AUTH] Requesting a new access token from Ring..."
        )

        try:
            response = requests.post(
                RING_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": token.refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={
                    "Accept": "application/json",
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            raise CommandError(
                f"Unable to contact Ring OAuth server: {exc}"
            )

        # ------------------------------------------------------------
        # Check Ring response
        # ------------------------------------------------------------

        if response.status_code != 200:
            # Never print the access/refresh token.
            try:
                error_data = response.json()
            except ValueError:
                error_data = response.text[:500]

            raise CommandError(
                f"Ring token refresh failed "
                f"(HTTP {response.status_code}): {error_data}"
            )

        try:
            data = response.json()
        except ValueError:
            raise CommandError(
                "Ring returned HTTP 200 but the response was not JSON."
            )

        new_access_token = data.get("access_token")

        if not new_access_token:
            raise CommandError(
                "Ring returned a successful response but no access_token."
            )

        # ------------------------------------------------------------
        # Save the new credentials
        # ------------------------------------------------------------

        token.access_token = new_access_token

        # Ring may rotate the refresh token.
        # If it does, ALWAYS save the new one.
        new_refresh_token = data.get("refresh_token")

        if new_refresh_token:
            token.refresh_token = new_refresh_token

        if data.get("token_type"):
            token.token_type = data["token_type"]

        if data.get("scope"):
            token.scope = data["scope"]

        if data.get("expires_in") is not None:
            token.expires_in = int(data["expires_in"])

        token.save()

        # ------------------------------------------------------------
        # Success
        # ------------------------------------------------------------

        self.stdout.write(
            self.style.SUCCESS(
                "[RING AUTH] Ring access token successfully refreshed."
            )
        )

        self.stdout.write(
            f"[RING AUTH] Account: {token.account_id}"
        )

        self.stdout.write(
            f"[RING AUTH] Expires in: {token.expires_in} seconds"
        )

