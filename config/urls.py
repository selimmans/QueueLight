from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

from dashboard.urls import api_urlpatterns, platform_urlpatterns

urlpatterns = [
    path("", RedirectView.as_view(url="/staff/login/", permanent=False)),
    path("admin/", admin.site.urls),
    path("q/", include("customer.urls")),
    path("staff/", include("dashboard.urls")),
    path("api/", include((api_urlpatterns, "dashboard_api"))),
    path("health/", include("core.urls")),
    path("platform/", include((platform_urlpatterns, "platform"))),
]
