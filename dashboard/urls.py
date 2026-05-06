from django.urls import path

from dashboard import views

app_name = "dashboard"

urlpatterns = [
    path("login/", views.StaffUnifiedLoginView.as_view(), name="unified_login"),
    path("<slug:slug>/login/", views.StaffLoginView.as_view(), name="login"),
    path("<slug:slug>/logout/", views.StaffLogoutView.as_view(), name="logout"),
    path("<slug:slug>/", views.DashboardView.as_view(), name="dashboard"),
    path("<slug:slug>/settings/", views.SettingsView.as_view(), name="settings"),
    path("<slug:slug>/next/", views.CallNextView.as_view(), name="call_next"),
    path("<slug:slug>/complete-batch/", views.CompleteBatchView.as_view(), name="complete_batch"),
    path("<slug:slug>/skip/<int:entry_id>/", views.SkipEntryView.as_view(), name="skip_entry"),
    path("<slug:slug>/complete/<int:entry_id>/", views.CompleteEntryView.as_view(), name="complete_entry"),
    path("<slug:slug>/noshow/<int:entry_id>/", views.NoShowEntryView.as_view(), name="noshow_entry"),
    path("<slug:slug>/qr.png", views.QRCodeView.as_view(), name="qr_code"),
    path("<slug:slug>/qr-poster/", views.QRPosterView.as_view(), name="qr_poster"),
    path("<slug:slug>/qr-poster/download/", views.QRPosterPNGView.as_view(), name="qr_poster_png"),
    path("<slug:slug>/pickup/<int:entry_id>/ready/", views.PickupReadyView.as_view(), name="pickup_ready"),
    path("<slug:slug>/pickup/<int:entry_id>/picked-up/", views.PickupPickedUpView.as_view(), name="pickup_picked_up"),
    path("<slug:slug>/pickup/closing-soon/", views.PickupClosingSoonView.as_view(), name="pickup_closing_soon"),
    path("<slug:slug>/pickup/clear/", views.PickupClearView.as_view(), name="pickup_clear"),
]

api_urlpatterns = [
    path("queue/<slug:slug>/status/", views.QueueStatusAPIView.as_view(), name="queue_status"),
    path("pickup/<slug:slug>/status/", views.PickupStatusAPIView.as_view(), name="pickup_status"),
]

platform_urlpatterns = [
    path("login/", views.PlatformLoginView.as_view(), name="platform_login"),
    path("logout/", views.PlatformLogoutView.as_view(), name="platform_logout"),
    path("", views.PlatformDashboardView.as_view(), name="platform"),
]
