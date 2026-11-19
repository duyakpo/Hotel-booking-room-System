from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from datetime import datetime, timedelta
from apps.core.models import Room, RoomType, Booking, Invoice
import uuid

def home(request):
    """UI-01: Trang chủ"""
    rooms = Room.objects.filter(status='AVAILABLE')
    return render(request, 'customer/UI_01_home.html', {'rooms': rooms})

def room_list(request):
    """UI-02: Danh sách phòng"""
    rooms = Room.objects.filter(status='AVAILABLE')
    return render(request, 'customer/UI_02_room_list.html', {'rooms': rooms})

def room_detail(request, room_id):
    """UI-03: Chi tiết phòng"""
    room = get_object_or_404(Room, room_id=room_id)
    return render(request, 'customer/UI_03_room_detail.html', {'room': room})
# 1. UC-07 & UC-08 & UC-09 & UC-13: ĐẶT PHÒNG 3 BƯỚC, GIỮ PHÒNG 10 PHÚT, TÍNH VAT 10%
def booking_step3_checkout(request, room_id):
    room = get_object_or_404(Room, room_id=room_id)

    # Kiểm tra phòng có đang bị giữ 10 phút bởi người khác không (Overbooking control)
    if room.is_locked() and room.status != 'AVAILABLE':
        return render(request, 'customer/error.html', {
            'message': 'Phòng này đang trong phiên giữ chỗ 10 phút của khách khác. Vui lòng chọn phòng khác hoặc đợi hết thời gian!'
        })

    if request.method == 'POST':
        guest_name = request.POST.get('guest_name')
        guest_phone = request.POST.get('guest_phone')
        guest_email = request.POST.get('guest_email')
        check_in_str = request.POST.get('check_in')
        check_out_str = request.POST.get('check_out')
        special_requests = request.POST.get('special_requests', '')
        payment_method = request.POST.get('payment_method', 'CARD')
        extra_bed = request.POST.get('extra_bed') == 'on' # Dịch vụ giường phụ (UC-08)

        # Tính số đêm ở
        d1 = datetime.strptime(check_in_str, '%Y-%m-%d')
        d2 = datetime.strptime(check_out_str, '%Y-%m-%d')
        nights = max((d2 - d1).days, 1)

        # Tính tiền tự động + 10% VAT (NFR & UC-07)
        room_charge = room.room_type.base_price * nights
        service_charge = 300000 if extra_bed else 0 # 300.000đ giường phụ
        sub_total = room_charge + service_charge
        vat_amount = sub_total * 0.1 # Thuế 10% VAT
        total_amount = sub_total + vat_amount

        # Tạo đơn đặt phòng & tự sinh mã BK-XXXXXX (Model tự sinh mã)
        booking = Booking.objects.create(
            room=room,
            customer=request.user if request.user.is_authenticated else None,
            guest_name=guest_name,
            guest_phone=guest_phone,
            guest_email=guest_email,
            check_in_date=d1,
            check_out_date=d2,
            special_requests=special_requests,
            total_amount=total_amount,
            booking_status='CONFIRMED' if payment_method != 'PAY_AT_HOTEL' else 'PENDING_APPROVAL'
        )

        # Khóa phòng 10 phút (status = RESERVED, locked_until = now + 10m)
        room.status = 'RESERVED'
        room.locked_until = timezone.now() + timedelta(minutes=10)
        room.save()

        # Tự động tạo Hóa đơn điện tử Invoice (UC-13)
        Invoice.objects.create(
            booking=booking,
            room_charge=room_charge,
            service_charge=service_charge,
            vat_amount=vat_amount,
            total_paid=total_amount,
            payment_method=payment_method,
            transaction_code=f"TXN-{uuid.uuid4().hex[:8].upper()}",
            idempotency_key=str(uuid.uuid4()), # Chống thanh toán trùng
            payment_status='PAID' if payment_method != 'PAY_AT_HOTEL' else 'PENDING'
        )

        return render(request, 'customer/UI_04_success.html', {'booking': booking})

    return render(request, 'customer/UI_04_booking_flow.html', {'room': room})


# 2. UC-11 & UC-12: THUẬT TOÁN HỦY PHÒNG & TỰ ĐỘNG HOÀN TIỀN
def cancel_booking_process(request, booking_id):
    booking = get_object_or_404(Booking, booking_id=booking_id)
    # Gọi thuật toán tính tiền hoàn trong model (Mốc 72h, 24h)
    refund_amount, penalty_fee = booking.calculate_cancellation_refund()

    if request.method == 'POST':
        # Cập nhật trạng thái đơn
        booking.booking_status = 'CANCELLED'
        booking.save()

        # Tự động nhả phòng về trạng thái AVAILABLE
        room = booking.room
        room.status = 'AVAILABLE'
        room.locked_until = None
        room.save()

        # Cập nhật hóa đơn
        if hasattr(booking, 'invoice'):
            booking.invoice.refund_amount = refund_amount
            booking.invoice.payment_status = 'REFUNDED'
            booking.invoice.save()

        return render(request, 'customer/cancel_success.html', {
            'booking': booking,
            'refund_amount': refund_amount,
            'penalty_fee': penalty_fee
        })

    return render(request, 'customer/cancel_confirm.html', {
        'booking': booking,
        'refund_amount': refund_amount,
        'penalty_fee': penalty_fee
    })