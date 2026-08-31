import logging

import requests

from django.conf import settings

from .models import RingToken


logger = logging.getLogger(__name__)


class RingAPI:

    def __init__(self):

        self.base_url = (
            settings.RING_API_BASE
        )

        self.oauth_url = (
            settings.RING_OAUTH_URL
        )

    def get_token(self):

        return (
            RingToken.objects
            .order_by("-updated_at")
            .first()
        )

    def refresh_token(self):

        token = self.get_token()

        if not token:

            raise RuntimeError(
                "No Ring token exists."
            )

        logger.info(
            "Refreshing Ring access token"
        )

        response = requests.post(

            self.oauth_url,

            data={
                "grant_type":
                    "refresh_token",

                "refresh_token":
                    token.refresh_token,

                "client_id":
                    settings.RING_CLIENT_ID,

                "client_secret":
                    settings.RING_CLIENT_SECRET,
            },

            timeout=30,
        )

        logger.info(
            "Ring OAuth returned HTTP %s",
            response.status_code,
        )

        response.raise_for_status()

        data = response.json()

        token.access_token = (
            data["access_token"]
        )

        if data.get("refresh_token"):

            token.refresh_token = (
                data["refresh_token"]
            )

        token.expires_in = data.get(
            "expires_in",
            14400,
        )

        token.token_type = data.get(
            "token_type",
            "Bearer",
        )

        token.scope = data.get(
            "scope",
            "",
        )

        token.save()

        return token

    def request(
        self,
        method,
        endpoint,
        **kwargs,
    ):

        token = self.get_token()

        if not token:

            raise RuntimeError(
                "No Ring token available."
            )

        headers = kwargs.pop(
            "headers",
            {},
        )

        headers["Authorization"] = (
            "Bearer "
            + token.access_token
        )

        headers.setdefault(
            "Accept",
            "application/json",
        )

        url = (
            self.base_url
            + endpoint
        )

        logger.info(
            "Ring API %s %s",
            method.upper(),
            endpoint,
        )

        response = requests.request(
            method,
            url,
            headers=headers,
            timeout=30,
            **kwargs,
        )

        logger.info(
            "Ring API HTTP %s",
            response.status_code,
        )

        if response.status_code == 401:

            logger.warning(
                "Ring token rejected; refreshing"
            )

            token = (
                self.refresh_token()
            )

            headers["Authorization"] = (
                "Bearer "
                + token.access_token
            )

            response = requests.request(
                method,
                url,
                headers=headers,
                timeout=30,
                **kwargs,
            )

        response.raise_for_status()

        return response.json()

    def get_user(self):

        return self.request(
            "GET",
            "/v1/users/me",
        )

    def get_devices(self):

        return self.request(
            "GET",
            "/v1/devices",
        )

    def get_device_status(
        self,
        device_id,
    ):

        return self.request(
            "GET",
            f"/v1/devices/{device_id}/status",
        )

    def get_device_capabilities(
        self,
        device_id,
    ):

        return self.request(
            "GET",
            f"/v1/devices/{device_id}/capabilities",
        )