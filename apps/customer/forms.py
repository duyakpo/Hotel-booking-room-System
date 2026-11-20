"""Form kiểm tra dữ liệu đầu vào cho các chức năng của Khách hàng (UC-01, UC-02, UC-10, UC-14)."""
from datetime import timedelta

from django import forms
from django.utils import timezone

from apps.core.models import Booking

DATE_INPUT_FORMATS = ['%Y-%m-%d', '%d/%m/%Y']

REVIEW_COMMENT_MIN_LENGTH = 10
REVIEW_COMMENT_MAX_LENGTH = 1000

SORT_PRICE_ASC = 'price_asc'
SORT_PRICE_DESC = 'price_desc'
SORT_RATING_DESC = 'rating_desc'
SORT_CHOICES = [
    (SORT_PRICE_ASC, 'Giá: thấp đến cao'),
    (SORT_PRICE_DESC, 'Giá: cao đến thấp'),
    (SORT_RATING_DESC, 'Đánh giá cao nhất'),
]


def normalize_phone(raw):
    """Chuẩn hóa SĐT Việt Nam: bỏ ký tự không phải số, đổi tiền tố 84 thành 0.

    VD: '+84 901-234-567' -> '0901234567'
    """
    digits = ''.join(ch for ch in (raw or '') if ch.isdigit())
    if digits.startswith('84') and len(digits) == 11:
        digits = '0' + digits[2:]
    return digits


def validate_stay_dates(check_in, check_out, today=None):
    """Kiểm tra ràng buộc ngày lưu trú (mục 2.1 đặc tả).

    - Ngày nhận phòng phải từ hôm nay trở đi (theo giờ Asia/Ho_Chi_Minh).
    - Ngày trả phòng phải sau ngày nhận phòng ít nhất 1 đêm.

    Trả về dict {tên_trường: thông_báo_lỗi}; dict rỗng nghĩa là hợp lệ.
    """
    today = today or timezone.localdate()
    errors = {}
    if check_in < today:
        errors['check_in'] = 'Ngày nhận phòng phải từ hôm nay trở đi.'
    if check_out < check_in + timedelta(days=1):
        errors['check_out'] = 'Ngày trả phòng phải sau ngày nhận phòng.'
    return errors


class RoomSearchForm(forms.Form):
    """UC-01: Tìm kiếm + lọc + sắp xếp phòng.

    Ngày nhận/trả phòng là tùy chọn: không nhập thì chỉ duyệt danh sách phòng
    (không kiểm tra phòng trống). Nếu nhập thì phải nhập đủ cả hai.
    Loại phòng (room_type) và tiện ích (amenities) là danh sách, đọc trực tiếp
    bằng request.GET.getlist() trong view vì có thể chọn nhiều giá trị.
    """

    check_in = forms.DateField(required=False, input_formats=DATE_INPUT_FORMATS)
    check_out = forms.DateField(required=False, input_formats=DATE_INPUT_FORMATS)
    adults = forms.IntegerField(required=False, min_value=1, max_value=20)
    children = forms.IntegerField(required=False, min_value=0, max_value=20)

    min_price = forms.DecimalField(required=False, min_value=0)
    max_price = forms.DecimalField(required=False, min_value=0)

    sort = forms.ChoiceField(required=False, choices=SORT_CHOICES)
    page = forms.IntegerField(required=False, min_value=1)

    def clean(self):
        cleaned = super().clean()
        check_in = cleaned.get('check_in')
        check_out = cleaned.get('check_out')

        if bool(check_in) != bool(check_out) and not self.has_error('check_in') \
                and not self.has_error('check_out'):
            missing = 'check_out' if check_in else 'check_in'
            self.add_error(missing, 'Vui lòng nhập đủ ngày nhận phòng và ngày trả phòng.')
        elif check_in and check_out:
            for field, message in validate_stay_dates(check_in, check_out).items():
                self.add_error(field, message)

        min_price = cleaned.get('min_price')
        max_price = cleaned.get('max_price')
        if min_price is not None and max_price is not None and min_price > max_price:
            self.add_error('max_price', 'Giá tối đa phải lớn hơn hoặc bằng giá tối thiểu.')

        return cleaned


class StayDatesForm(forms.Form):
    """UC-02: Ngày lưu trú (tùy chọn) để tính bảng giá theo đêm trên trang chi tiết."""

    check_in = forms.DateField(required=False, input_formats=DATE_INPUT_FORMATS)
    check_out = forms.DateField(required=False, input_formats=DATE_INPUT_FORMATS)

    def clean(self):
        cleaned = super().clean()
        check_in = cleaned.get('check_in')
        check_out = cleaned.get('check_out')
        if check_in and check_out:
            for field, message in validate_stay_dates(check_in, check_out).items():
                self.add_error(field, message)
        return cleaned


class BookingLookupForm(forms.Form):
    """UC-10: Tra cứu đơn theo Số điện thoại hoặc Mã booking."""

    phone = forms.CharField(required=False, max_length=20)
    booking_code = forms.CharField(required=False, max_length=20)
    status = forms.ChoiceField(required=False,
                               choices=[('', 'Tất cả')] + list(Booking.STATUS_CHOICES))
    page = forms.IntegerField(required=False, min_value=1)

    def clean_phone(self):
        return normalize_phone(self.cleaned_data.get('phone'))

    def clean_booking_code(self):
        return (self.cleaned_data.get('booking_code') or '').strip().upper()

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('phone') and not cleaned.get('booking_code'):
            raise forms.ValidationError('Vui lòng nhập Số điện thoại hoặc Mã booking.')
        return cleaned


class ReviewForm(forms.Form):
    """UC-14: Gửi đánh giá. Xác thực chủ đơn bằng Mã booking + Số điện thoại đặt phòng."""

    booking_code = forms.CharField(max_length=20)
    phone = forms.CharField(max_length=20)
    rating = forms.IntegerField(
        min_value=1, max_value=5,
        error_messages={
            'min_value': 'Số sao phải từ 1 đến 5.',
            'max_value': 'Số sao phải từ 1 đến 5.',
            'invalid': 'Số sao phải là số nguyên từ 1 đến 5.',
        },
    )
    comment = forms.CharField(strip=True)

    def clean_booking_code(self):
        return self.cleaned_data['booking_code'].strip().upper()

    def clean_phone(self):
        return normalize_phone(self.cleaned_data['phone'])

    def clean_comment(self):
        comment = self.cleaned_data['comment']
        if len(comment) < REVIEW_COMMENT_MIN_LENGTH:
            raise forms.ValidationError(
                f'Nội dung đánh giá phải có ít nhất {REVIEW_COMMENT_MIN_LENGTH} ký tự.')
        if len(comment) > REVIEW_COMMENT_MAX_LENGTH:
            raise forms.ValidationError(
                f'Nội dung đánh giá tối đa {REVIEW_COMMENT_MAX_LENGTH} ký tự.')
        return comment
