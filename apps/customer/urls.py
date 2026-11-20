from django.urls import path

from . import views

app_name = 'customer'

urlpatterns = [
    # UC-01: Tìm kiếm & lọc phòng
    path('rooms/', views.room_list, name='room_list'),
    path('api/rooms/search/', views.api_room_search, name='api_room_search'),

    # UC-02: Chi tiết phòng
    path('rooms/<int:room_id>/', views.room_detail, name='room_detail'),
    path('api/rooms/<int:room_id>/', views.api_room_detail, name='api_room_detail'),

    # UC-10: Tra cứu lịch sử đặt phòng
    path('api/bookings/lookup/', views.api_booking_lookup, name='api_booking_lookup'),

    # UC-14: Đánh giá phòng
    path('api/reviews/', views.api_submit_review, name='api_submit_review'),
]
