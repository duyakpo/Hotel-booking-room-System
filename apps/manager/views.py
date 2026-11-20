from datetime import date

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render

from apps.core.models import Booking, Room


@login_required
def manager_dashboard(request):
    today = date.today()

    # --- KPI 1: Doanh thu tháng này ---
    # Cộng tiền các đơn CONFIRMED, STAYING, COMPLETED trong tháng
    # (Booking chưa có ngày tạo đơn nên tạm tính theo ngày check-in)
    ket_qua = Booking.objects.filter(
        status__in=["CONFIRMED", "STAYING", "COMPLETED"],
        check_in_date__year=today.year,
        check_in_date__month=today.month,
    ).aggregate(tong=Sum("total_amount"))
    revenue = ket_qua["tong"]
    if revenue is None:
        revenue = 0

    # --- KPI 2: Tỷ lệ lấp đầy phòng ---
    # = số phòng OCCUPIED / tổng số phòng * 100
    total_rooms = Room.objects.count()
    occupied_rooms = Room.objects.filter(status="OCCUPIED").count()
    if total_rooms > 0:
        occupancy_rate = round(occupied_rooms / total_rooms * 100, 1)
    else:
        occupancy_rate = 0

    # --- KPI 3: Số đơn đặt phòng hôm nay ---
    bookings_today = Booking.objects.filter(check_in_date=today).count()

    # --- KPI 4: Tỷ lệ hủy phòng ---
    # = số đơn CANCELLED / tổng số đơn * 100
    total_bookings = Booking.objects.count()
    cancelled = Booking.objects.filter(status="CANCELLED").count()
    if total_bookings > 0:
        cancel_rate = round(cancelled / total_bookings * 100, 1)
    else:
        cancel_rate = 0

    # 5 đơn mới nhất cho bảng "Recent bookings"
    recent_bookings = Booking.objects.order_by("-id")[:5]

    context = {
        "revenue": revenue,
        "occupancy_rate": occupancy_rate,
        "bookings_today": bookings_today,
        "cancel_rate": cancel_rate,
        "recent_bookings": recent_bookings,
    }
    return render(request, "manager/UI_07_dashboard.html", context)
