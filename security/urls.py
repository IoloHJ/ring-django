from django.urls import path

from . import views


urlpatterns = [
    path("login/", views.security_login, name="security-login"),
    path("logout/", views.security_logout, name="security-logout"),
    path("2fa/setup/", views.security_2fa_setup_pending, name="security-2fa-setup"),
    path("2fa/setup/qr/", views.security_2fa_qr, name="security-2fa-qr"),
    path("2fa/verify/", views.security_2fa_verify, name="security-2fa-verify"),
    path("api/app/activate/", views.security_app_activate, name="security-app-activate"),
    path("api/app/deactivate/", views.security_app_deactivate, name="security-app-deactivate"),
]
