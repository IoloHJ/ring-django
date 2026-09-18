import json

import pyotp
from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import AppInstallation, SecurityProfile
from .services import hash_app_token


class SecurityFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="iolo",
            password="Valid-password-1!",
        )
        self.profile = SecurityProfile.objects.create(
            user=self.user,
            totp_secret=pyotp.random_base32(),
        )

    def test_first_login_requires_and_enables_totp(self):
        response = self.client.post(
            "/security/login/",
            {"username": "iolo", "password": "Valid-password-1!"},
        )
        self.assertRedirects(response, "/security/2fa/setup/")

        code = pyotp.TOTP(self.profile.totp_secret).now()
        response = self.client.post("/security/2fa/verify/", {"code": code})

        self.assertRedirects(response, "/ring/alerts/")
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.totp_enabled)
        self.assertEqual(self.client.session.get_expire_at_browser_close(), False)
        self.assertEqual(self.client.session.get_expiry_age(), 12 * 60 * 60)

    def test_app_activation_and_deactivation(self):
        self.profile.totp_enabled = True
        self.profile.save(update_fields=["totp_enabled"])
        code = pyotp.TOTP(self.profile.totp_secret).now()
        response = self.client.post(
            "/security/api/app/activate/",
            data=json.dumps({
                "username": "iolo",
                "password": "Valid-password-1!",
                "code": code,
                "installation_id": "test-installation",
                "platform": "ios",
                "app_version": "0.0.1",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        token = response.json()["token"]
        installation = AppInstallation.objects.get(installation_id="test-installation")
        self.assertEqual(installation.token_hash, hash_app_token(token))

        response = self.client.post(
            "/security/api/app/deactivate/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 200)
        installation.refresh_from_db()
        self.assertFalse(installation.is_active)
