"""
Unit test cho UC-01, UC-02, UC-10, UC-14 (dùng model trong apps.core).

Chạy:  python manage.py test apps.customer.tests
"""
import warnings
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import include, path, reverse
from django.utils import timezone

from apps.core.models import Booking, Review, Room, RoomType

from .forms import normalize_phone
from .views import (
    filter_rooms, find_bookings, get_room_detail, room_has_amenity, search_available_rooms,
    submit_review,
)

urlpatterns = [path('', include('apps.customer.urls'))]


def codes(bookings):
    # Lưu ý: so sánh theo mã, không dùng ==, vì pk của model core là CharField
    # mặc định uuid.uuid4 (object mới tạo có pk kiểu UUID, đọc từ DB lại là str).
    return {b.booking_code for b in bookings}


def at(day, hour):
    """Datetime aware theo giờ địa phương (GMT+7)."""
    return timezone.make_aware(datetime.combine(day, time(hour, 0)))


class BaseData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()
        cls.single = RoomType.objects.create(type_name='Single', base_price=500000)
        cls.double = RoomType.objects.create(type_name='Double', base_price=900000)
        cls.suite = RoomType.objects.create(type_name='Suite', base_price=2500000)
        cls.family = RoomType.objects.create(type_name='Family', base_price=1800000)

        cls.r101 = Room.objects.create(room_number='101', room_type=cls.single, floor=1,
                                       capacity=1, amenities=['Wi-Fi miễn phí'])
        cls.r201 = Room.objects.create(room_number='201', room_type=cls.double, floor=2,
                                       capacity=3, amenities=['Wi-Fi miễn phí', 'Hồ bơi'])
        cls.r301 = Room.objects.create(
            room_number='301', room_type=cls.suite, floor=3, capacity=4,
            amenities=['WiFi tốc độ cao', 'Swimming pool', 'Bồn tắm cao cấp'],
            images=[f'images/rooms/301_{i}.jpg' for i in range(12)])
        cls.r401 = Room.objects.create(room_number='401', room_type=cls.family, floor=4,
                                       capacity=6, amenities=['Wi-Fi', 'Bồn tắm'],
                                       status='OCCUPIED')
        cls.r102 = Room.objects.create(room_number='102', room_type=cls.single, floor=1,
                                       status='MAINTENANCE')

    def make_booking(self, room, check_in, nights=2, status='CONFIRMED', **kw):
        defaults = dict(guest_name='Nguyễn Văn A', guest_phone='0901234567',
                        guest_email='khach@example.com',
                        total_amount=room.room_type.base_price * nights)
        defaults.update(kw)
        return Booking.objects.create(
            room=room, check_in_date=at(check_in, 14),
            check_out_date=at(check_in + timedelta(days=nights), 12),
            booking_status=status, **defaults)


# ---------------------------------------------------------------------------
# UC-01
# ---------------------------------------------------------------------------
class SearchAvailableRoomsTests(BaseData):
    def ids(self, qs):
        return set(qs.values_list('room_number', flat=True))

    def test_rejects_check_in_in_the_past(self):
        with self.assertRaises(ValidationError) as ctx:
            search_available_rooms(self.today - timedelta(days=1), self.today + timedelta(days=1))
        self.assertIn('check_in', ctx.exception.message_dict)

    def test_rejects_check_out_not_after_check_in(self):
        for co in (self.today, self.today - timedelta(days=1)):
            with self.assertRaises(ValidationError) as ctx:
                search_available_rooms(self.today, co)
            self.assertIn('check_out', ctx.exception.message_dict)

    def test_check_in_today_allowed_and_maintenance_excluded(self):
        rooms = search_available_rooms(self.today, self.today + timedelta(days=1))
        # 401 đang OCCUPIED hôm nay nhưng không có đơn nào trùng ngày -> vẫn hiển thị
        self.assertEqual(self.ids(rooms), {'101', '201', '301', '401'})

    def test_excludes_rooms_with_overlapping_bookings(self):
        ci = self.today + timedelta(days=5)
        self.make_booking(self.r201, ci, nights=3)
        self.make_booking(self.r301, ci, status='STAYING')
        self.make_booking(self.r401, ci, status='CANCELLED')     # đơn đã hủy: không chặn
        self.make_booking(self.r101, ci, status='COMPLETED')     # đơn đã xong: không chặn
        rooms = search_available_rooms(ci + timedelta(days=1), ci + timedelta(days=2))
        self.assertEqual(self.ids(rooms), {'101', '401'})

    def test_back_to_back_stays_do_not_conflict(self):
        ci = self.today + timedelta(days=5)
        self.make_booking(self.r201, ci, nights=2)  # trả phòng 12:00 ngày ci+2
        self.assertIn('201', self.ids(
            search_available_rooms(ci + timedelta(days=2), ci + timedelta(days=4))))
        self.assertNotIn('201', self.ids(
            search_available_rooms(ci - timedelta(days=1), ci + timedelta(days=1))))

    def test_naive_midnight_dates_from_booking_flow(self):
        """booking_step3_checkout lưu ngày dạng datetime naive lúc 00:00 — vẫn phải khớp."""
        ci = self.today + timedelta(days=3)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            Booking.objects.create(
                room=self.r201, guest_name='B', guest_phone='0911111111',
                guest_email='b@example.com', total_amount=1,
                check_in_date=datetime.combine(ci, time()),
                check_out_date=datetime.combine(ci + timedelta(days=1), time()),
                booking_status='PENDING_APPROVAL')
        self.assertNotIn('201', self.ids(search_available_rooms(ci, ci + timedelta(days=1))))
        self.assertIn('201', self.ids(
            search_available_rooms(ci + timedelta(days=1), ci + timedelta(days=2))))

    def test_pending_payment_blocks_only_within_hold_window(self):
        ci = self.today + timedelta(days=3)
        self.make_booking(self.r201, ci, status='PENDING_PAYMENT')
        old = self.make_booking(self.r301, ci, status='PENDING_PAYMENT')
        Booking.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(minutes=11))
        ids = self.ids(search_available_rooms(ci, ci + timedelta(days=1)))
        self.assertNotIn('201', ids)
        self.assertIn('301', ids)

    def test_capacity(self):
        ci, co = self.today, self.today + timedelta(days=1)
        self.assertEqual(self.ids(search_available_rooms(ci, co, adults=2)), {'201', '301', '401'})
        self.assertEqual(self.ids(search_available_rooms(ci, co, adults=2, children=2)),
                         {'301', '401'})
        self.assertEqual(self.ids(search_available_rooms(ci, co, adults=7)), set())


class FilterRoomsTests(BaseData):
    def ids(self, **kw):
        return set(filter_rooms(Room.objects.all(), **kw).values_list('room_number', flat=True))

    def test_amenity_matching_ignores_accents_and_case(self):
        self.assertTrue(room_has_amenity(['Wi-Fi miễn phí'], 'wifi'))
        self.assertTrue(room_has_amenity(['Hồ bơi vô cực'], 'pool'))
        self.assertTrue(room_has_amenity(['Hồ bơi'], 'hồ bơi'))
        self.assertFalse(room_has_amenity(['Bồn tắm'], 'pool'))
        self.assertFalse(room_has_amenity(None, 'wifi'))

    def test_filter_by_room_type_case_insensitive(self):
        self.assertEqual(self.ids(room_types=['suite', 'FAMILY']), {'301', '401'})

    def test_filter_by_price_range_inclusive(self):
        self.assertEqual(self.ids(min_price=900000, max_price=1800000), {'201', '401'})
        self.assertEqual(self.ids(min_price=2000000), {'301'})

    def test_filter_by_amenities_requires_all(self):
        self.assertEqual(self.ids(amenity_codes=['pool']), {'201', '301'})
        self.assertEqual(self.ids(amenity_codes=['pool', 'bathtub']), {'301'})

    def test_combined_filters(self):
        self.assertEqual(
            self.ids(room_types=['Double', 'Suite', 'Family'], max_price=2000000,
                     amenity_codes=['wifi']),
            {'201', '401'})


@override_settings(ROOT_URLCONF='apps.customer.tests')
class RoomSearchViewTests(BaseData):
    def search(self, **params):
        return self.client.get(reverse('api_room_search'), params)

    def test_api_search_filters_and_sorts(self):
        ci = self.today + timedelta(days=1)
        res = self.search(check_in=ci.isoformat(), check_out=(ci + timedelta(days=2)).isoformat(),
                          adults=2, amenities='wifi', sort='price_desc')
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual([r['room_number'] for r in body['results']], ['301', '401', '201'])
        self.assertEqual(body['results'][0]['estimated_total'], 5000000)
        self.assertEqual(body['results'][2]['price_per_night_display'], '900.000 đ')
        self.assertTrue(body['results'][0]['thumbnail'].startswith('/static/'))

    def test_multi_value_params(self):
        res = self.client.get(reverse('api_room_search') + '?room_type=single&room_type=suite')
        self.assertEqual({r['room_number'] for r in res.json()['results']}, {'101', '301'})
        res = self.search(amenities='pool,bathtub')
        self.assertEqual([r['room_number'] for r in res.json()['results']], ['301'])

    def test_accepts_dd_mm_yyyy(self):
        ci = self.today + timedelta(days=1)
        res = self.search(check_in=ci.strftime('%d/%m/%Y'),
                          check_out=(ci + timedelta(days=1)).strftime('%d/%m/%Y'))
        self.assertEqual(res.status_code, 200)

    def test_invalid_input_returns_400(self):
        self.assertIn('check_out', self.search(check_in=self.today.isoformat(),
                                               check_out=self.today.isoformat()).json()['errors'])
        self.assertEqual(self.search(check_in=self.today.isoformat()).status_code, 400)
        self.assertEqual(self.search(min_price=2000000, max_price=1000000).status_code, 400)
        self.assertEqual(self.search(sort='abc').status_code, 400)

    def test_no_result_message(self):
        body = self.search(adults=10).json()
        self.assertEqual(body['count'], 0)
        self.assertTrue(body['message'])

    def test_sort_by_rating(self):
        for room, rating in ((self.r101, 3), (self.r401, 5)):
            b = self.make_booking(room, self.today - timedelta(days=5), status='COMPLETED')
            Review.objects.create(booking=b, rating=rating, comment='x' * 20)
        numbers = [r['room_number'] for r in self.search(sort='rating_desc').json()['results']]
        self.assertEqual(numbers[:2], ['401', '101'])

    def test_html_room_list(self):
        res = self.client.get(reverse('room_list'), {'room_type': 'single'})
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'customer/UI_02_room_list.html')
        self.assertEqual([r.room_number for r in res.context['rooms']], ['101'])
        self.assertIn('Suite', res.context['room_type_choices'])


# ---------------------------------------------------------------------------
# UC-02
# ---------------------------------------------------------------------------
@override_settings(ROOT_URLCONF='apps.customer.tests')
class RoomDetailTests(BaseData):
    def test_detail_limits_images_and_includes_policy(self):
        detail = get_room_detail(self.r301.room_id)
        self.assertEqual(len(detail['images']), 10)
        self.assertEqual(len(detail['cancellation_policy']), 3)
        self.assertEqual(len(detail['amenities']), 3)
        self.assertIsNone(detail['price_summary'])

    def test_price_summary_with_vat(self):
        ci = self.today + timedelta(days=1)
        detail = get_room_detail(self.r301.room_id, ci, ci + timedelta(days=2))
        summary = detail['price_summary']
        self.assertEqual(summary['nights'], 2)
        self.assertEqual(summary['subtotal'], Decimal('5000000'))
        self.assertEqual(summary['vat'], Decimal('500000'))
        self.assertEqual(summary['total'], Decimal('5500000'))
        self.assertTrue(detail['is_available'])

    def test_reports_unavailable_dates(self):
        ci = self.today + timedelta(days=1)
        self.make_booking(self.r301, ci)
        self.assertFalse(
            get_room_detail(self.r301.room_id, ci, ci + timedelta(days=1))['is_available'])

    def test_api_detail_json_with_reviews(self):
        b = self.make_booking(self.r301, self.today - timedelta(days=5), status='COMPLETED')
        Review.objects.create(booking=b, rating=4, comment='Phòng rất đẹp',
                              manager_reply='Cảm ơn quý khách')
        res = self.client.get(reverse('api_room_detail', args=[self.r301.room_id]))
        self.assertEqual(res.status_code, 200)
        room = res.json()['room']
        self.assertEqual(room['name'], 'Suite - Phòng 301')
        self.assertEqual(len(room['images']), 10)
        self.assertEqual(room['avg_rating'], 4.0)
        self.assertEqual(room['reviews'][0]['manager_reply'], 'Cảm ơn quý khách')

    def test_api_detail_invalid_dates(self):
        res = self.client.get(reverse('api_room_detail', args=[self.r301.room_id]),
                              {'check_in': self.today.isoformat(),
                               'check_out': self.today.isoformat()})
        self.assertEqual(res.status_code, 400)

    def test_html_detail(self):
        res = self.client.get(reverse('room_detail', args=[self.r201.room_id]))
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'customer/UI_03_room_detail.html')
        self.assertEqual(res.context['room'].room_number, '201')

    def test_not_found(self):
        self.assertEqual(self.client.get(reverse('room_detail', args=['khong-ton-tai'])).status_code, 404)
        self.assertEqual(self.client.get(reverse('api_room_detail', args=['x'])).status_code, 404)

    def test_maintenance_room_redirects_to_search(self):
        res = self.client.get(reverse('room_detail', args=[self.r102.room_id]))
        self.assertRedirects(res, reverse('room_list'))
        res = self.client.get(reverse('api_room_detail', args=[self.r102.room_id]))
        self.assertEqual(res.status_code, 410)


# ---------------------------------------------------------------------------
# UC-10
# ---------------------------------------------------------------------------
@override_settings(ROOT_URLCONF='apps.customer.tests')
class BookingLookupTests(BaseData):
    def setUp(self):
        self.b1 = self.make_booking(self.r201, self.today + timedelta(days=3),
                                    guest_phone='090 123 4567')
        self.b2 = self.make_booking(self.r301, self.today - timedelta(days=10),
                                    status='COMPLETED', guest_phone='+84901234567')
        self.other = self.make_booking(self.r401, self.today, guest_phone='0988888888')

    def test_normalize_phone(self):
        self.assertEqual(normalize_phone('+84 901-234-567'), '0901234567')

    def test_find_by_phone_in_any_format(self):
        self.assertEqual(codes(find_bookings(phone='0901234567')),
                         {self.b1.booking_code, self.b2.booking_code})

    def test_find_by_booking_code(self):
        self.assertTrue(self.other.booking_code.startswith('BK-'))
        self.assertEqual(codes(find_bookings(booking_code=self.other.booking_code.lower())),
                         {self.other.booking_code})

    def test_find_requires_a_criterion(self):
        with self.assertRaises(ValidationError):
            find_bookings()

    def test_api_lookup(self):
        body = self.client.get(reverse('api_booking_lookup'), {'phone': '84901234567'}).json()
        self.assertEqual(body['count'], 2)
        self.assertEqual(body['status_counts'], {'CONFIRMED': 1, 'COMPLETED': 1})
        by_code = {b['booking_code']: b for b in body['results']}
        self.assertTrue(by_code[self.b1.booking_code]['can_cancel'])
        self.assertEqual(by_code[self.b1.booking_code]['nights'], 2)
        self.assertTrue(by_code[self.b2.booking_code]['can_review'])

    def test_api_lookup_status_tab(self):
        res = self.client.get(reverse('api_booking_lookup'),
                              {'phone': '0901234567', 'status': 'COMPLETED'})
        self.assertEqual([b['booking_code'] for b in res.json()['results']],
                         [self.b2.booking_code])

    def test_api_lookup_errors_and_empty(self):
        self.assertEqual(self.client.get(reverse('api_booking_lookup')).status_code, 400)
        body = self.client.get(reverse('api_booking_lookup'), {'booking_code': 'BK-000000'}).json()
        self.assertEqual(body['count'], 0)
        self.assertTrue(body['message'])


# ---------------------------------------------------------------------------
# UC-14
# ---------------------------------------------------------------------------
@override_settings(ROOT_URLCONF='apps.customer.tests')
class SubmitReviewTests(BaseData):
    def setUp(self):
        self.done = self.make_booking(self.r301, self.today - timedelta(days=5),
                                      status='COMPLETED')

    def review(self, **kw):
        args = dict(booking_code=self.done.booking_code, phone='0901234567', rating=5,
                    comment='Phòng sạch sẽ, nhân viên thân thiện.')
        args.update(kw)
        return submit_review(**args)

    def test_creates_review(self):
        self.assertEqual(self.review().booking.booking_code, self.done.booking_code)

    def test_rating_must_be_1_to_5(self):
        for bad in (0, 6, '5', 4.5, True):
            with self.assertRaises(ValidationError):
                self.review(rating=bad)

    def test_comment_length(self):
        with self.assertRaises(ValidationError):
            self.review(comment='   ngắn   ')
        with self.assertRaises(ValidationError):
            self.review(comment='a' * 1001)
        self.assertEqual(self.review(comment='  ' + 'a' * 10 + '  ').comment, 'a' * 10)

    def test_only_once_per_booking(self):
        self.review()
        with self.assertRaises(ValidationError):
            self.review()

    def test_booking_must_be_completed(self):
        b = self.make_booking(self.r201, self.today + timedelta(days=2))
        with self.assertRaises(ValidationError):
            self.review(booking_code=b.booking_code)

    def test_phone_must_match_booking(self):
        with self.assertRaises(ValidationError):
            self.review(phone='0911111111')

    def test_within_30_days_after_checkout(self):
        old = self.make_booking(self.r201, self.today - timedelta(days=40), status='COMPLETED')
        with self.assertRaises(ValidationError):
            self.review(booking_code=old.booking_code)

    def test_api_submit_form_and_json(self):
        url = reverse('api_submit_review')
        res = self.client.post(url, {'booking_code': self.done.booking_code,
                                     'phone': '0901234567', 'rating': 4,
                                     'comment': 'Rất hài lòng với kỳ nghỉ.'})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()['room_avg_rating'], 4.0)

        other = self.make_booking(self.r301, self.today - timedelta(days=3), status='COMPLETED')
        res = self.client.post(url, {'booking_code': other.booking_code, 'phone': '0901234567',
                                     'rating': 2, 'comment': 'Điều hòa hơi ồn.'},
                               content_type='application/json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()['room_avg_rating'], 3.0)

    def test_api_validation_errors(self):
        url = reverse('api_submit_review')
        res = self.client.post(url, {'booking_code': self.done.booking_code,
                                     'phone': '0901234567', 'rating': 7, 'comment': 'ngắn'})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(set(res.json()['errors']), {'rating', 'comment'})
        res = self.client.post(url, {'booking_code': self.done.booking_code,
                                     'phone': '0999999999', 'rating': 5,
                                     'comment': 'Nội dung hợp lệ đủ dài'})
        self.assertEqual(res.status_code, 400)
        self.assertIn('message', res.json())

    def test_api_requires_post(self):
        self.assertEqual(self.client.get(reverse('api_submit_review')).status_code, 405)
