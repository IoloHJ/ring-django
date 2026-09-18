from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("security/", include("security.urls")),
    path("", include("ring_api.urls")),
]
