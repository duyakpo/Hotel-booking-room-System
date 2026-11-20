from django.urls import path

from . import views

urlpatterns = [
    # ---- Trang giao diện (HTML) ----
    path('', views.home, name='home'),                                           # Trang chủ UI-01
    path('rooms/', views.room_list, name='room_list'),                           # Danh sách phòng UI-02 (UC-01)
    path('rooms/<str:room_id>/', views.room_detail, name='room_detail'),         # Chi tiết phòng UI-03 (UC-02)
    path('book/<str:room_id>/', views.booking_step3_checkout, name='book_room'),# Đặt phòng 3 bước UI-04
    path('cancel/<str:booking_id>/', views.cancel_booking_process, name='cancel_booking'),

    # ---- API JSON (gọi bằng AJAX từ giao diện) ----
    path('api/rooms/search/', views.api_room_search, name='api_room_search'),              # UC-01: lọc không tải lại trang
    path('api/rooms/<str:room_id>/', views.api_room_detail, name='api_room_detail'),      # UC-02: giá theo ngày đã chọn
    path('api/bookings/lookup/', views.api_booking_lookup, name='api_booking_lookup'),    # UC-10: tra cứu theo SĐT / mã booking
    path('api/reviews/', views.api_submit_review, name='api_submit_review'),              # UC-14: gửi đánh giá (POST)
]
