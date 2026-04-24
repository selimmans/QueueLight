from django.contrib import admin
from django.urls import path, include

from dashboard.urls import api_urlpatterns

urlpatterns = [
    path("admin/", admin.site.urls),
    path("q/", include("customer.urls")),
    path("staff/", include("dashboard.urls")),
    path("api/", include((api_urlpatterns, "dashboard_api"))),
    path("health/", include("core.urls")),
]
