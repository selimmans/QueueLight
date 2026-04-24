from django.urls import path

from customer import views

app_name = "customer"

urlpatterns = [
    path("<slug:slug>/", views.JoinView.as_view(), name="join"),
    path("<slug:slug>/confirmation/<int:entry_id>/", views.ConfirmView.as_view(), name="confirmation"),
]
