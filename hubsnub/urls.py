from django.urls import include, path
from django.views.generic import RedirectView

from notifications.admin import hubsnub_admin

urlpatterns = [
    path("", RedirectView.as_view(url="/admin/", permanent=False)),
    path("admin/", hubsnub_admin.urls),
    path("webhooks/", include("notifications.urls")),
]
