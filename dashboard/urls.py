from django.urls import path

from dashboard import views

app_name = "dashboard"

urlpatterns = [
    path("<slug:slug>/login/", views.StaffLoginView.as_view(), name="login"),
    path("<slug:slug>/logout/", views.StaffLogoutView.as_view(), name="logout"),
    path("<slug:slug>/", views.DashboardView.as_view(), name="dashboard"),
    path("<slug:slug>/next/", views.CallNextView.as_view(), name="call_next"),
]

api_urlpatterns = [
    path("queue/<slug:slug>/status/", views.QueueStatusAPIView.as_view(), name="queue_status"),
]
