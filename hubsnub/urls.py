from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from notifications.admin import hubsnub_admin

admin.site.site_header = (
    "HubSnub Administration"  # The main header on each page (and above the login form)
)
admin.site.site_title = "HubSnub"  # The HTML title tag (browser tab name)
admin.site.index_title = (
    "Welcome to HubSnub Admin"  # The text at the top of the admin index page
)


urlpatterns = [
    path("", RedirectView.as_view(url="/admin/", permanent=False)),
    path("admin/", hubsnub_admin.urls),
    path("webhooks/", include("notifications.urls")),
]
