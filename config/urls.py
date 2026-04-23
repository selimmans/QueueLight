from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("q/", include("customer.urls")),
    path("staff/", include("dashboard.urls")),
    path("health/", include("core.urls")),
]
