from django.contrib.auth import get_user_model
from django.test import TestCase


class LoginRedirectTests(TestCase):
    def test_anonymous_browser_is_sent_to_login(self):
        response = self.client.get("/ring/alerts/", HTTP_ACCEPT="text/html")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/security/login/", response["Location"])

    def test_json_api_is_not_redirected_by_browser_login_middleware(self):
        response = self.client.get("/ring/alerts/api/", HTTP_ACCEPT="application/json")

        self.assertNotEqual(response.status_code, 302)

    def test_authenticated_user_can_open_site(self):
        user = get_user_model().objects.create_user(
            username="signed-in",
            password="test-password",
        )
        self.client.force_login(user)

        response = self.client.get("/ring/alerts/", HTTP_ACCEPT="text/html")

        self.assertEqual(response.status_code, 200)
