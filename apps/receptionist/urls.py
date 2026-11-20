path("room-rack/", views.room_rack, name="room_rack"),
path("rooms/<int:room_id>/status/", views.update_room_status, name="update_room_status"),
