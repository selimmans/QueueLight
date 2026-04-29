from django.urls import path

from customer import views

app_name = "customer"

urlpatterns = [
    path("<slug:slug>/", views.JoinView.as_view(), name="join"),
    path("<slug:slug>/confirmation/<int:entry_id>/", views.ConfirmView.as_view(), name="confirmation"),
    path("<slug:slug>/status/<int:entry_id>/", views.CustomerStatusView.as_view(), name="status"),
    path("<slug:slug>/response/<int:entry_id>/", views.CustomerResponseView.as_view(), name="response"),
    path("<slug:slug>/leave/<int:entry_id>/", views.LeaveQueueView.as_view(), name="leave"),
    path("<slug:slug>/pickup/", views.PickupJoinView.as_view(), name="pickup_join"),
    path("<slug:slug>/pickup/confirmation/<int:entry_id>/", views.PickupConfirmView.as_view(), name="pickup_confirmation"),
]
