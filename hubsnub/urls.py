from django.urls import include, path

from notifications.admin import hubsnub_admin

urlpatterns = [
    path("admin/", hubsnub_admin.urls),
    path("webhooks/", include("notifications.urls")),
]
