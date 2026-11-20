from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.models import Room

# Màu hiển thị theo trạng thái phòng
MAU_PHONG = {
    "AVAILABLE": "green",     # Xanh lá: Trống
    "OCCUPIED": "red",        # Đỏ: Có khách
    "CLEANING": "yellow",     # Vàng: Đang dọn
    "RESERVED": "blue",       # Xanh dương: Đã đặt
    "MAINTENANCE": "gray",    # Xám: Bảo trì
}


@login_required
def room_rack(request):
    # Lấy ngày muốn xem từ URL (?date=2026-11-20), nếu không có thì lấy hôm nay
    ngay_str = request.GET.get("date")
    if ngay_str:
        try:
            view_date = datetime.strptime(ngay_str, "%Y-%m-%d").date()
        except ValueError:
            view_date = date.today()
    else:
        view_date = date.today()

    # Lấy tất cả phòng, tầng cao xếp trước (Tầng 4 -> Tầng 1)
    rooms = Room.objects.all().order_by("-floor", "room_number")

    # Gom phòng theo từng tầng
    floors = []
    tang_hien_tai = None
    for room in rooms:
        if tang_hien_tai is None or tang_hien_tai["floor"] != room.floor:
            tang_hien_tai = {"floor": room.floor, "rooms": [], "available": 0}
            floors.append(tang_hien_tai)

        tang_hien_tai["rooms"].append({
            "id": room.id,
            "room_number": room.room_number,
            "room_type": room.room_type.name,
            "status": room.status,
            "color": MAU_PHONG.get(room.status, "gray"),
        })
        if room.status == "AVAILABLE":
            tang_hien_tai["available"] += 1

    # Đếm số phòng theo từng trạng thái cho phần chú thích màu
    legend = []
    for status in MAU_PHONG:
        so_luong = rooms.filter(status=status).count()
        legend.append({"status": status, "color": MAU_PHONG[status], "count": so_luong})

    context = {
        "floors": floors,
        "legend": legend,
        "total_rooms": rooms.count(),
        "view_date": view_date,
        "read_only": view_date < date.today(),  # ngày quá khứ chỉ xem
    }
    return render(request, "receptionist/UI_06_room_rack.html", context)


@login_required
def update_room_status(request, room_id):
    # UC-24: đổi CLEANING -> AVAILABLE, hoặc sang MAINTENANCE
    if request.method != "POST":
        return redirect("receptionist:room_rack")

    room = get_object_or_404(Room, pk=room_id)
    new_status = request.POST.get("status")

    # Phòng đang có khách thì không được đổi
    if room.status == "OCCUPIED":
        messages.error(request, "Phòng đang có khách, không thể đổi trạng thái!")
    elif new_status not in ["AVAILABLE", "MAINTENANCE"]:
        messages.error(request, "Trạng thái mới không hợp lệ!")
    else:
        room.status = new_status
        room.save()
        messages.success(request, "Đã cập nhật phòng " + str(room.room_number))

    return redirect("receptionist:room_rack")
