from django.urls import path

from . import views

app_name = "receptionist"

urlpatterns = [
    path("bookings/<int:booking_id>/check-in/", views.check_in, name="check_in"),
    path("bookings/<int:booking_id>/check-out/", views.check_out, name="check_out"),
    path("bookings/<int:booking_id>/services/", views.add_service, name="add_service"),
    path("bookings/<int:booking_id>/no-show/", views.handle_no_show, name="handle_no_show"),
]
