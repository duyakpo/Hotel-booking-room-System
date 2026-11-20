"""
Views nhóm Khách hàng (apps/customer).

    UI-01  home                             Trang chủ
    UC-01  room_list / api_room_search      Tìm kiếm & lọc phòng (UI-02 / JSON)
    UC-02  room_detail / api_room_detail    Chi tiết phòng (UI-03 / JSON)
    UC-07  booking_step3_checkout           Đặt phòng 3 bước (UI-04)
    UC-10  api_booking_lookup               Tra cứu lịch sử đặt phòng (JSON)
    UC-11  cancel_booking_process           Hủy phòng & hoàn tiền
    UC-14  api_submit_review                Đánh giá phòng (JSON, POST)
"""
import json
import unicodedata
import uuid
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Exists, F, OuterRef, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.core.models import Booking, Invoice, Review, Room, RoomType

from .forms import (
    REVIEW_COMMENT_MAX_LENGTH, REVIEW_COMMENT_MIN_LENGTH, SORT_CHOICES, SORT_PRICE_DESC,
    SORT_RATING_DESC, BookingLookupForm, ReviewForm, RoomSearchForm, StayDatesForm,
    normalize_phone, validate_stay_dates,
)


def home(request):
    """UI-01: Trang chủ"""
    rooms = Room.objects.filter(status='AVAILABLE')
    return render(request, 'customer/UI_01_home.html', {'rooms': rooms})


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


# ===========================================================================
# UC-01, UC-02, UC-10, UC-14 — Tìm kiếm phòng, chi tiết phòng, tra cứu đơn, đánh giá
#
# Các hàm nghiệp vụ (search_available_rooms, filter_rooms, get_room_detail,
# find_bookings, submit_review, ...) tách riêng khỏi view để dễ viết unit test
# và dùng lại ở module khác (VD: quy trình đặt phòng UC-07).
# ===========================================================================

# Hằng số nghiệp vụ (theo đặc tả; sau này lấy từ bảng SystemConfig - UC-33)
CHECK_IN_TIME = time(14, 0)
CHECK_OUT_TIME = time(12, 0)
HOLD_MINUTES = 10
VAT_RATE = Decimal('0.10')
MAX_ROOM_IMAGES = 10
REVIEW_WINDOW_DAYS = 30
ROOMS_PER_PAGE = 10
BOOKINGS_PER_PAGE = 10
DATE_DISPLAY_FORMAT = '%d/%m/%Y'

# Trạng thái đơn đang chiếm phòng (chặn người khác đặt trùng ngày).
# PENDING_PAYMENT chỉ chiếm phòng trong HOLD_MINUTES phút kể từ lúc tạo đơn.
OCCUPYING_STATUSES = ('PENDING_APPROVAL', 'CONFIRMED', 'STAYING')
CANCELLABLE_STATUSES = ('PENDING_PAYMENT', 'PENDING_APPROVAL', 'CONFIRMED')
UNSELLABLE_ROOM_STATUSES = ('MAINTENANCE',)

NO_ROOMS_MESSAGE = ('Không tìm thấy phòng phù hợp trong khoảng thời gian này. '
                    'Vui lòng chọn ngày khác hoặc giảm bớt bộ lọc.')
ROOM_UNAVAILABLE_MESSAGE = 'Phòng này hiện không còn phục vụ. Vui lòng chọn phòng khác.'

# Chính sách hủy phòng tiêu chuẩn (mục 3.5), tính so với 14:00 ngày nhận phòng.
CANCELLATION_POLICY = [
    {'code': 'FREE', 'condition': 'Hủy trước hơn 72 giờ',
     'description': 'Miễn phí hủy, hoàn 100% số tiền đã thanh toán.'},
    {'code': 'FIRST_NIGHT', 'condition': 'Hủy trong khoảng 24 - 72 giờ',
     'description': 'Phí phạt bằng tiền phòng đêm đầu tiên.'},
    {'code': 'NON_REFUNDABLE', 'condition': 'Hủy trong vòng 24 giờ',
     'description': 'Không hoàn tiền.'},
]

# Room.amenities trong apps.core là danh sách chuỗi tự do (JSON), VD:
#   ["Wi-Fi miễn phí", "Bồn tắm", "Hồ bơi"]
# Bộ lọc nhận mã tiện ích (wifi, pool, ...) và so khớp theo từ khóa (bỏ dấu, không
# phân biệt hoa thường). Mã không có trong bảng này sẽ được dùng chính nó làm từ khóa.
AMENITY_FILTERS = {
    'wifi': ('Wi-Fi', ['wifi', 'wi-fi', 'internet']),
    'air_conditioner': ('Điều hòa', ['dieu hoa', 'may lanh', 'air conditioner',
                                     'air conditioning']),
    'bathtub': ('Bồn tắm', ['bon tam', 'bathtub']),
    'parking': ('Bãi đỗ xe', ['do xe', 'bai xe', 'parking']),
    'pool': ('Hồ bơi', ['ho boi', 'be boi', 'swimming pool', 'pool']),
    'sea_view': ('View biển', ['view bien', 'huong bien', 'sea view']),
}


# ---------------------------------------------------------------------------
# Tiện ích chung
# ---------------------------------------------------------------------------
def format_vnd(amount):
    """1200000 -> '1.200.000 đ'"""
    value = int(Decimal(amount or 0).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    return f'{value:,}'.replace(',', '.') + ' đ'


def to_local_date(value):
    """DateTimeField (aware/naive) hoặc date -> date theo giờ địa phương (GMT+7)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return timezone.localtime(value).date() if timezone.is_aware(value) else value.date()
    return value


def format_date(value):
    value = to_local_date(value)
    return value.strftime(DATE_DISPLAY_FORMAT) if value else None


def image_src(item):
    """Ảnh trong Room.images có thể là chuỗi đường dẫn hoặc dict {'url': ...}."""
    path = item.get('url') if isinstance(item, dict) else item
    if not path:
        return None
    path = str(path)
    if path.startswith(('http://', 'https://', '/')):
        return path
    return static(path)


def room_display_name(room):
    return f'{room.room_type.type_name} - Phòng {room.room_number}'


def form_errors(form):
    return {field: [str(e) for e in errs] for field, errs in form.errors.items()}


def _plain_text(text):
    """'Wi-Fi miễn phí' -> 'wifimienphi' (bỏ dấu, bỏ ký tự đặc biệt, chữ thường)."""
    text = str(text).replace('đ', 'd').replace('Đ', 'D')
    text = unicodedata.normalize('NFD', text)
    return ''.join(ch for ch in text if ch.isalnum() and not unicodedata.combining(ch)).lower()


def _getlist(params, key):
    """Đọc tham số nhiều giá trị: ?k=a&k=b hoặc ?k=a,b"""
    if hasattr(params, 'getlist'):
        raw = params.getlist(key)
    else:
        value = params.get(key)
        raw = value if isinstance(value, (list, tuple)) else ([value] if value else [])
    values = []
    for item in raw:
        values.extend(v.strip() for v in str(item).split(',') if v.strip())
    return values


# ---------------------------------------------------------------------------
# UC-01: Tìm kiếm phòng trống + bộ lọc + sắp xếp
# ---------------------------------------------------------------------------
def overlapping_bookings(check_in, check_out, now=None):
    """Các đơn đang chiếm phòng và giao với khoảng lưu trú [check_in, check_out).

    Hai khoảng giao nhau khi: đơn.check_in < check_out VÀ đơn.check_out > check_in
    (khách trả phòng 12:00 ngày X thì khách khác vẫn nhận được phòng 14:00 ngày X).
    So sánh theo NGÀY (giờ địa phương) vì Booking.check_in_date là DateTimeField.
    """
    now = now or timezone.now()
    return Booking.objects.filter(
        check_in_date__date__lt=check_out,
        check_out_date__date__gt=check_in,
    ).filter(
        Q(booking_status__in=OCCUPYING_STATUSES)
        | Q(booking_status='PENDING_PAYMENT',
            created_at__gt=now - timedelta(minutes=HOLD_MINUTES))
    )


def sellable_rooms():
    """Phòng đang hoạt động (loại bỏ phòng bảo trì / tạm ngưng)."""
    return Room.objects.exclude(status__in=UNSELLABLE_ROOM_STATUSES)


def filter_by_capacity(rooms, adults=None, children=None):
    """Tổng số khách (người lớn + trẻ em) không vượt quá sức chứa của phòng."""
    return rooms.filter(capacity__gte=(adults or 1) + (children or 0))


def search_available_rooms(check_in, check_out, adults=1, children=0, now=None):
    """UC-01: Tìm các phòng còn trống trong khoảng ngày và đủ sức chứa số khách.

    Ràng buộc (ném ValidationError nếu vi phạm):
      - check_in >= hôm nay
      - check_out >= check_in + 1 đêm
      - adults >= 1, children >= 0

    Phòng được coi là trống khi:
      - không ở trạng thái MAINTENANCE, và
      - không có đơn nào đang chiếm phòng giao với khoảng ngày yêu cầu.
    (Room.status AVAILABLE/RESERVED/OCCUPIED/CLEANING chỉ phản ánh *hôm nay*; với
    ngày trong tương lai, tình trạng trống được tính từ bảng Booking.)
    """
    errors = validate_stay_dates(check_in, check_out)
    if adults is None or adults < 1:
        errors['adults'] = 'Số người lớn phải từ 1 trở lên.'
    if children is not None and children < 0:
        errors['children'] = 'Số trẻ em không hợp lệ.'
    if errors:
        raise ValidationError(errors)

    busy = overlapping_bookings(check_in, check_out, now=now).filter(room=OuterRef('pk'))
    rooms = sellable_rooms().filter(~Exists(busy))
    return filter_by_capacity(rooms, adults, children)


def room_has_amenity(amenities, wanted):
    """Phòng (danh sách tiện ích dạng chuỗi) có tiện ích `wanted` (mã hoặc tên) hay không."""
    key = wanted.strip().lower()
    keywords = AMENITY_FILTERS[key][1] if key in AMENITY_FILTERS else [wanted]
    keywords = [_plain_text(k) for k in keywords if _plain_text(k)]
    items = [_plain_text(a) for a in (amenities or [])]
    return any(k in item for k in keywords for item in items)


def filter_rooms(rooms, room_types=None, min_price=None, max_price=None, amenity_codes=None):
    """UC-01 (Filter): lọc đồng thời theo loại phòng, khoảng giá và tiện ích.

    - room_types: danh sách tên loại phòng (Single, Double, Suite, Family, ...) — khớp
      1 trong các loại, không phân biệt hoa thường.
    - min_price / max_price: khoảng giá mỗi đêm (VND), tính cả hai đầu mút.
    - amenity_codes: danh sách mã/tên tiện ích — phòng phải có ĐỦ tất cả tiện ích đã chọn.
    """
    if room_types:
        type_q = Q()
        for name in room_types:
            type_q |= Q(room_type__type_name__iexact=name.strip())
        rooms = rooms.filter(type_q)
    if min_price is not None:
        rooms = rooms.filter(room_type__base_price__gte=min_price)
    if max_price is not None:
        rooms = rooms.filter(room_type__base_price__lte=max_price)
    if amenity_codes:
        # Room.amenities là JSONField — SQLite không hỗ trợ lookup __contains cho JSON,
        # nên lọc tiện ích bằng Python trên tập phòng đã thu hẹp ở các bước trên.
        matched = [pk for pk, amenities in rooms.values_list('pk', 'amenities')
                   if all(room_has_amenity(amenities, code) for code in amenity_codes)]
        rooms = rooms.filter(pk__in=matched)
    return rooms


def with_rating(rooms):
    return rooms.annotate(
        avg_rating=Avg('bookings__review__rating'),
        review_count=Count('bookings__review', distinct=True),
    )


def sort_rooms(rooms, sort=None):
    """UC-01 (Sort): giá tăng dần (mặc định), giá giảm dần, điểm đánh giá giảm dần."""
    if sort == SORT_PRICE_DESC:
        return rooms.order_by('-room_type__base_price', 'room_number')
    if sort == SORT_RATING_DESC:
        return rooms.order_by(F('avg_rating').desc(nulls_last=True),
                              'room_type__base_price', 'room_number')
    return rooms.order_by('room_type__base_price', 'room_number')


def run_room_search(params):
    """Chạy toàn bộ luồng UC-01 từ query params. Dùng chung cho view HTML và JSON.

    Trả về dict: form, is_valid, page (Page | None), total, searched_dates.
    """
    form = RoomSearchForm(params)
    if not form.is_valid():
        return {'form': form, 'is_valid': False, 'page': None, 'total': 0,
                'searched_dates': False}

    data = form.cleaned_data
    check_in, check_out = data.get('check_in'), data.get('check_out')
    adults, children = data.get('adults') or 1, data.get('children') or 0

    if check_in and check_out:
        rooms = search_available_rooms(check_in, check_out, adults, children)
    else:
        rooms = filter_by_capacity(sellable_rooms(), adults, children)

    rooms = filter_rooms(
        rooms,
        room_types=_getlist(params, 'room_type'),
        min_price=data.get('min_price'),
        max_price=data.get('max_price'),
        amenity_codes=_getlist(params, 'amenities'),
    )
    rooms = sort_rooms(with_rating(rooms.select_related('room_type')), data.get('sort'))
    page = Paginator(rooms, ROOMS_PER_PAGE).get_page(data.get('page') or 1)
    return {'form': form, 'is_valid': True, 'page': page, 'total': page.paginator.count,
            'searched_dates': bool(check_in and check_out)}


def serialize_room_card(room, nights=None):
    images = list(room.images or [])
    avg = getattr(room, 'avg_rating', None)
    data = {
        'id': str(room.room_id),
        'room_number': room.room_number,
        'name': room_display_name(room),
        'room_type': {'id': str(room.room_type.type_id), 'name': room.room_type.type_name},
        'floor': room.floor,
        'area': room.area,
        'capacity': room.capacity,
        'status': room.status,
        'price_per_night': int(room.room_type.base_price),
        'price_per_night_display': format_vnd(room.room_type.base_price),
        'thumbnail': image_src(images[0]) if images else None,
        'amenities': list(room.amenities or []),
        'avg_rating': round(avg, 1) if avg is not None else None,
        'review_count': getattr(room, 'review_count', 0),
        'free_cancellation_label': 'Miễn phí hủy trước 72h',
    }
    if nights:
        data['nights'] = nights
        data['estimated_total'] = int(room.room_type.base_price * nights)
    return data


def _search_filters_context():
    return {
        'room_type_choices': list(
            RoomType.objects.order_by('base_price').values_list('type_name', flat=True)),
        'amenity_choices': [{'code': code, 'name': label}
                            for code, (label, _) in AMENITY_FILTERS.items()],
        'sort_choices': SORT_CHOICES,
        'room_type_counts': dict(
            sellable_rooms().order_by().values_list('room_type__type_name')
            .annotate(n=Count('pk'))),
    }


@require_GET
def room_list(request):
    """UI-02: Danh sách phòng — tìm kiếm, lọc, sắp xếp (render HTML)."""
    result = run_room_search(request.GET)
    context = {
        **result,
        **_search_filters_context(),
        'rooms': result['page'].object_list if result['page'] else [],
        'selected_room_types': _getlist(request.GET, 'room_type'),
        'selected_amenities': _getlist(request.GET, 'amenities'),
        'no_rooms_message': NO_ROOMS_MESSAGE if result['is_valid'] and not result['total'] else None,
    }
    return render(request, 'customer/UI_02_room_list.html', context)


@require_GET
def api_room_search(request):
    """API JSON cho UC-01 — dùng cho bộ lọc AJAX (cập nhật kết quả không cần tải lại trang)."""
    result = run_room_search(request.GET)
    if not result['is_valid']:
        return JsonResponse({'ok': False, 'errors': form_errors(result['form'])}, status=400)

    data = result['form'].cleaned_data
    nights = (data['check_out'] - data['check_in']).days if result['searched_dates'] else None
    page = result['page']
    return JsonResponse({
        'ok': True,
        'count': result['total'],
        'message': None if result['total'] else NO_ROOMS_MESSAGE,
        'page': page.number,
        'num_pages': page.paginator.num_pages,
        'results': [serialize_room_card(r, nights) for r in page.object_list],
    })


# ---------------------------------------------------------------------------
# UC-02: Xem chi tiết phòng
# ---------------------------------------------------------------------------
def get_nightly_rates(room, check_in, check_out):
    """Bảng giá theo từng đêm trong khoảng lưu trú.

    Hiện dùng giá cơ bản của loại phòng (khớp với cách tính tiền ở booking_step3_checkout).
    Khi áp dụng PricingRule (UC-26) chỉ cần sửa hàm này.
    """
    nights = []
    day = check_in
    while day < check_out:
        nights.append({'date': day, 'price': room.room_type.base_price})
        day += timedelta(days=1)
    return nights


def calculate_price_summary(room, check_in, check_out):
    nightly = get_nightly_rates(room, check_in, check_out)
    subtotal = sum((n['price'] for n in nightly), Decimal('0'))
    vat = (subtotal * VAT_RATE).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return {
        'nightly_rates': nightly,
        'nights': len(nightly),
        'subtotal': subtotal,
        'vat_rate': VAT_RATE,
        'vat': vat,
        'total': subtotal + vat,
    }


def is_room_available(room, check_in, check_out, now=None):
    if room.status in UNSELLABLE_ROOM_STATUSES:
        return False
    return not overlapping_bookings(check_in, check_out, now=now).filter(room=room).exists()


def get_room_detail(room_id, check_in=None, check_out=None):
    """UC-02: Lấy toàn bộ thông tin hiển thị trên trang chi tiết phòng (UI-03).

    Ném Http404 nếu phòng không tồn tại. Nếu có check_in/check_out (đã hợp lệ)
    thì kèm bảng giá theo đêm, tổng tiền dự kiến (gồm VAT 10%) và tình trạng còn trống.
    """
    room = get_object_or_404(Room.objects.select_related('room_type'), room_id=room_id)
    reviews = Review.objects.filter(booking__room=room).select_related('booking') \
        .order_by('-created_at')
    stats = reviews.aggregate(avg=Avg('rating'), count=Count('pk'))
    avg = stats['avg']

    detail = {
        'room': room,
        'room_name': room_display_name(room),
        'images': [image_src(i) for i in (room.images or [])[:MAX_ROOM_IMAGES]],
        'amenities': list(room.amenities or []),
        'cancellation_policy': CANCELLATION_POLICY,
        'check_in_time': CHECK_IN_TIME,
        'check_out_time': CHECK_OUT_TIME,
        'reviews': list(reviews),
        'avg_rating': round(avg, 1) if avg is not None else None,
        'review_count': stats['count'],
        'is_sellable': room.status not in UNSELLABLE_ROOM_STATUSES,
        'price_summary': None,
        'is_available': None,
    }
    if check_in and check_out:
        detail['price_summary'] = calculate_price_summary(room, check_in, check_out)
        detail['is_available'] = is_room_available(room, check_in, check_out)
    return detail


def serialize_room_detail(detail):
    room = detail['room']
    summary = detail['price_summary']
    return {
        'id': str(room.room_id),
        'room_number': room.room_number,
        'name': detail['room_name'],
        'room_type': {'id': str(room.room_type.type_id), 'name': room.room_type.type_name},
        'floor': room.floor,
        'area': room.area,
        'capacity': room.capacity,
        'description': room.room_type.description,
        'price_per_night': int(room.room_type.base_price),
        'price_per_night_display': format_vnd(room.room_type.base_price),
        'images': detail['images'],
        'amenities': detail['amenities'],
        'cancellation_policy': detail['cancellation_policy'],
        'check_in_time': detail['check_in_time'].strftime('%H:%M'),
        'check_out_time': detail['check_out_time'].strftime('%H:%M'),
        'avg_rating': detail['avg_rating'],
        'review_count': detail['review_count'],
        'reviews': [
            {
                'guest_name': r.booking.guest_name,
                'stay_date': format_date(r.booking.check_in_date),
                'rating': r.rating,
                'comment': r.comment,
                'verified_stay': True,
                'created_at': format_date(r.created_at),
                'manager_reply': r.manager_reply or None,
                'replied_at': format_date(r.replied_at),
            }
            for r in detail['reviews']
        ],
        'is_available': detail['is_available'],
        'price_summary': summary and {
            'nights': summary['nights'],
            'nightly_rates': [{'date': format_date(n['date']), 'price': int(n['price'])}
                              for n in summary['nightly_rates']],
            'subtotal': int(summary['subtotal']),
            'vat_rate': float(summary['vat_rate']),
            'vat': int(summary['vat']),
            'total': int(summary['total']),
            'total_display': format_vnd(summary['total']),
        },
    }


def _stay_dates(request):
    form = StayDatesForm(request.GET)
    if not form.is_valid():
        return form, None, None
    return form, form.cleaned_data.get('check_in'), form.cleaned_data.get('check_out')


@require_GET
def room_detail(request, room_id):
    """UI-03: Chi tiết phòng (render HTML)."""
    dates_form, check_in, check_out = _stay_dates(request)
    detail = get_room_detail(room_id, check_in, check_out)
    if not detail['is_sellable']:
        # Luồng thay thế UC-02: phòng chuyển sang bảo trì / tạm ngưng
        messages.warning(request, ROOM_UNAVAILABLE_MESSAGE)
        return redirect('room_list')
    return render(request, 'customer/UI_03_room_detail.html',
                  {**detail, 'dates_form': dates_form})


@require_GET
def api_room_detail(request, room_id):
    """API JSON cho UC-02 (VD: cập nhật giá khi khách đổi ngày ở hộp đặt phòng)."""
    dates_form, check_in, check_out = _stay_dates(request)
    if dates_form.errors:
        return JsonResponse({'ok': False, 'errors': form_errors(dates_form)}, status=400)
    detail = get_room_detail(room_id, check_in, check_out)
    if not detail['is_sellable']:
        return JsonResponse({'ok': False, 'message': ROOM_UNAVAILABLE_MESSAGE}, status=410)
    return JsonResponse({'ok': True, 'room': serialize_room_detail(detail)})


# ---------------------------------------------------------------------------
# UC-10: Tra cứu lịch sử đặt phòng
# ---------------------------------------------------------------------------
def find_bookings(phone=None, booking_code=None, status=None):
    """UC-10: Tra cứu đơn đặt phòng theo Số điện thoại hoặc Mã booking (BK-XXXXXX).

    - SĐT được chuẩn hóa ở cả hai phía ('090 123 4567', '+84901234567' đều khớp).
    - Nhập cả hai thì đơn phải khớp cả hai. Có thể lọc thêm theo trạng thái (tab).
    """
    if not phone and not booking_code:
        raise ValidationError('Vui lòng nhập Số điện thoại hoặc Mã booking.')

    bookings = Booking.objects.select_related('room__room_type', 'review')
    if booking_code:
        bookings = bookings.filter(booking_code__iexact=booking_code.strip())
    if phone:
        phone = normalize_phone(phone)
        candidates = Booking.objects.filter(guest_phone__contains=phone[-4:]) \
            .values_list('pk', 'guest_phone')
        bookings = bookings.filter(
            pk__in=[pk for pk, raw in candidates if normalize_phone(raw) == phone])
    if status:
        bookings = bookings.filter(booking_status=status)
    return bookings.order_by('-created_at')


def review_deadline(booking):
    checked_out = booking.actual_check_out or booking.check_out_date
    return checked_out + timedelta(days=REVIEW_WINDOW_DAYS)


def has_review(booking):
    try:
        return booking.review is not None
    except Review.DoesNotExist:
        return False


def can_review(booking, now=None):
    """Chỉ đánh giá khi: COMPLETED, chưa đánh giá, trong vòng 30 ngày sau check-out."""
    now = now or timezone.now()
    return (booking.booking_status == 'COMPLETED'
            and not has_review(booking)
            and now <= review_deadline(booking))


def serialize_booking(booking):
    room = booking.room
    images = list(room.images or [])
    check_in, check_out = to_local_date(booking.check_in_date), to_local_date(booking.check_out_date)
    return {
        'booking_id': str(booking.booking_id),
        'booking_code': booking.booking_code,
        'room': {
            'id': str(room.room_id),
            'room_number': room.room_number,
            'name': room_display_name(room),
            'thumbnail': image_src(images[0]) if images else None,
        },
        'guest_name': booking.guest_name,
        'check_in_date': format_date(check_in),
        'check_out_date': format_date(check_out),
        'nights': (check_out - check_in).days,
        'num_of_guests': booking.num_of_guests,
        'total_amount': int(booking.total_amount),
        'total_amount_display': format_vnd(booking.total_amount),
        'status': booking.booking_status,
        'status_display': booking.get_booking_status_display(),
        'special_requests': booking.special_requests or '',
        'created_at': format_date(booking.created_at),
        'can_cancel': booking.booking_status in CANCELLABLE_STATUSES,
        'can_review': can_review(booking),
        'has_review': has_review(booking),
    }


@require_GET
def api_booking_lookup(request):
    """API JSON cho UC-10: ?phone=...  hoặc  ?booking_code=...  (&status=...&page=...)"""
    form = BookingLookupForm(request.GET)
    if not form.is_valid():
        return JsonResponse({'ok': False, 'errors': form_errors(form)}, status=400)

    data = form.cleaned_data
    all_bookings = find_bookings(phone=data['phone'], booking_code=data['booking_code'])
    status_counts = dict(all_bookings.order_by().values_list('booking_status')
                         .annotate(n=Count('pk')))
    bookings = all_bookings.filter(booking_status=data['status']) if data.get('status') \
        else all_bookings

    page = Paginator(bookings, BOOKINGS_PER_PAGE).get_page(data.get('page') or 1)
    total = page.paginator.count
    return JsonResponse({
        'ok': True,
        'count': total,
        'status_counts': status_counts,
        'message': None if total else ('Không tìm thấy đơn đặt phòng phù hợp. '
                                       'Vui lòng kiểm tra lại Số điện thoại hoặc Mã booking.'),
        'page': page.number,
        'num_pages': page.paginator.num_pages,
        'results': [serialize_booking(b) for b in page.object_list],
    })


# ---------------------------------------------------------------------------
# UC-14: Đánh giá phòng
# ---------------------------------------------------------------------------
def submit_review(booking_code, phone, rating, comment, now=None):
    """UC-14: Lưu đánh giá cho một đơn và trả về Review vừa tạo.

    Ràng buộc (ném ValidationError nếu vi phạm):
      - rating là số nguyên 1..5; comment 10..1000 ký tự (sau khi bỏ khoảng trắng 2 đầu)
      - Mã booking + SĐT phải khớp cùng một đơn (xác thực chủ đơn)
      - Đơn ở trạng thái COMPLETED, trong vòng 30 ngày sau check-out
      - Mỗi đơn chỉ được đánh giá 1 lần
    """
    now = now or timezone.now()
    comment = (comment or '').strip()
    if not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 5:
        raise ValidationError({'rating': 'Số sao phải từ 1 đến 5.'})
    if len(comment) < REVIEW_COMMENT_MIN_LENGTH:
        raise ValidationError(
            {'comment': f'Nội dung đánh giá phải có ít nhất {REVIEW_COMMENT_MIN_LENGTH} ký tự.'})
    if len(comment) > REVIEW_COMMENT_MAX_LENGTH:
        raise ValidationError(
            {'comment': f'Nội dung đánh giá tối đa {REVIEW_COMMENT_MAX_LENGTH} ký tự.'})

    with transaction.atomic():
        booking = (Booking.objects.select_for_update()
                   .filter(booking_code__iexact=(booking_code or '').strip()).first())
        if booking is None or normalize_phone(booking.guest_phone) != normalize_phone(phone):
            raise ValidationError('Không tìm thấy đơn đặt phòng với Mã booking và SĐT đã nhập.')
        if booking.booking_status != 'COMPLETED':
            raise ValidationError('Chỉ có thể đánh giá sau khi đã hoàn tất lưu trú (check-out).')
        if Review.objects.filter(booking=booking).exists():
            raise ValidationError('Đơn đặt phòng này đã được đánh giá.')
        if now > review_deadline(booking):
            raise ValidationError(
                f'Đã quá {REVIEW_WINDOW_DAYS} ngày kể từ ngày trả phòng, không thể gửi đánh giá.')
        try:
            return Review.objects.create(booking=booking, rating=rating, comment=comment)
        except IntegrityError:
            raise ValidationError('Đơn đặt phòng này đã được đánh giá.')


def _request_data(request):
    if request.content_type == 'application/json':
        try:
            body = json.loads(request.body or b'{}')
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        return body if isinstance(body, dict) else None
    return request.POST


def _validation_error_payload(exc):
    if hasattr(exc, 'error_dict'):
        return {'errors': {k: [str(m) for e in v for m in e.messages]
                           for k, v in exc.error_dict.items()}}
    return {'message': ' '.join(exc.messages)}


@require_POST
def api_submit_review(request):
    """API JSON cho UC-14 (POST): booking_code, phone, rating (1-5), comment (10-1000 ký tự)."""
    data = _request_data(request)
    if data is None:
        return JsonResponse({'ok': False, 'message': 'Dữ liệu gửi lên không hợp lệ.'}, status=400)

    form = ReviewForm(data)
    if not form.is_valid():
        return JsonResponse({'ok': False, 'errors': form_errors(form)}, status=400)

    cleaned = form.cleaned_data
    try:
        review = submit_review(cleaned['booking_code'], cleaned['phone'],
                               cleaned['rating'], cleaned['comment'])
    except ValidationError as exc:
        return JsonResponse({'ok': False, **_validation_error_payload(exc)}, status=400)

    avg = Review.objects.filter(booking__room=review.booking.room) \
        .aggregate(avg=Avg('rating'))['avg']
    return JsonResponse({
        'ok': True,
        'message': 'Cảm ơn bạn đã gửi đánh giá!',
        'review': {
            'id': str(review.review_id),
            'booking_code': review.booking.booking_code,
            'rating': review.rating,
            'comment': review.comment,
            'verified_stay': True,
        },
        'room_avg_rating': round(avg, 1) if avg is not None else None,
    }, status=201)
