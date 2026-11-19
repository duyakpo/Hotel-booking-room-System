from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),                                           # Trang chủ UI-01
    path('rooms/', views.room_list, name='room_list'),                           # Danh sách phòng UI-02
    path('rooms/<str:room_id>/', views.room_detail, name='room_detail'),         # Chi tiết phòng UI-03
    path('book/<str:room_id>/', views.booking_step3_checkout, name='book_room'),# Đặt phòng 3 bước UI-04
    path('cancel/<str:booking_id>/', views.cancel_booking_process, name='cancel_booking'),
]