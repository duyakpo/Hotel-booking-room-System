from decimal import Decimal, InvalidOperation
from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import FieldDoesNotExist
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

def _model_by_names(*names):
    wanted = {name.lower() for name in names}
    for model in apps.get_models():
        if model.__name__.lower() in wanted:
            return model
    return None

def _concrete_fields(model):
    return [field for field in model._meta.get_fields() if getattr(field, 'concrete', False) and (not getattr(field, 'many_to_many', False))]

def _field_name(model, *candidates):
    by_lower = {field.name.lower(): field.name for field in _concrete_fields(model)}
    for candidate in candidates:
        if candidate.lower() in by_lower:
            return by_lower[candidate.lower()]
    return None

def _set_if_present(instance, candidates, value):
    name = _field_name(instance.__class__, *candidates)
    if name:
        setattr(instance, name, value)
        return name
    return None

def _get_attr(instance, candidates, default=None):
    for candidate in candidates:
        if hasattr(instance, candidate):
            value = getattr(instance, candidate)
            if not callable(value):
                return value
    return default

def _status_value(model, candidates, preferred):
    name = _field_name(model, *candidates)
    if not name:
        return None
    field = model._meta.get_field(name)
    choices = getattr(field, 'choices', None) or []
    if choices:
        flattened = []
        for value, label in choices:
            flattened.append((str(value), str(label)))
        preferred_words = {preferred.lower(), preferred.lower().replace('_', ' '), preferred.lower().replace('_', '')}
        for value, label in flattened:
            if value.lower() in preferred_words or label.lower() in preferred_words:
                return value
        alternatives = {'checked_in': ('check_in', 'in_house', 'occupied'), 'checked_out': ('check_out', 'completed', 'complete'), 'no_show': ('noshow', 'no-show', 'missed')}.get(preferred, ())
        for value, label in flattened:
            if value.lower() in alternatives or label.lower() in alternatives:
                return value
    return preferred

def _get_booking_or_error(booking_id):
    model = _model_by_names('Booking', 'Reservation', 'RoomBooking')
    if model is None:
        return (None, JsonResponse({'success': False, 'error': 'Không tìm thấy model Booking/Reservation. Cần bổ sung model nghiệp vụ để tích hợp chính xác.'}, status=501))
    try:
        booking = model.objects.select_for_update().get(pk=booking_id)
    except model.DoesNotExist:
        return (None, JsonResponse({'success': False, 'error': 'Không tìm thấy đơn đặt phòng.'}, status=404))
    return (booking, None)

def _receptionist_required(view_func):

    def wrapped(request, *args, **kwargs):
        user = request.user
        in_receptionist_group = user.is_authenticated and user.groups.filter(name__in=('receptionist', 'Receptionist', 'Lễ tân')).exists()
        if not (user.is_authenticated and (user.is_staff or user.is_superuser or in_receptionist_group)):
            return JsonResponse({'success': False, 'error': 'Bạn không có quyền thực hiện thao tác lễ tân.'}, status=403)
        return view_func(request, *args, **kwargs)
    wrapped.__name__ = view_func.__name__
    wrapped.__doc__ = view_func.__doc__
    return login_required(wrapped)

def _update_room_status(booking, status):
    room = _get_attr(booking, ('room', 'booked_room'))
    if room is None:
        return
    room_status_field = _field_name(room.__class__, 'status', 'room_status', 'availability_status')
    if room_status_field:
        room_status = _status_value(room.__class__, (room_status_field,), status)
        setattr(room, room_status_field, room_status)
        room.save(update_fields=[room_status_field])

def _booking_status_field(booking):
    return _field_name(booking.__class__, 'status', 'booking_status', 'reservation_status')

def _validate_transition(booking, target):
    current = _get_attr(booking, ('status', 'booking_status', 'reservation_status'))
    if current is None:
        return None
    current_text = str(current).lower().replace('-', '_').replace(' ', '_')
    allowed = {'checked_in': {'confirmed', 'booked', 'reserved', 'pending', 'approved', 'paid'}, 'checked_out': {'checked_in', 'in_house', 'occupied', 'checkedin'}, 'no_show': {'confirmed', 'booked', 'reserved', 'pending', 'approved'}}
    if current_text in {'checked_out', 'checkedout', 'cancelled', 'canceled', 'no_show', 'noshow'}:
        return f"Đơn đặt phòng đang ở trạng thái '{current}', không thể chuyển sang {target}."
    if target == 'checked_out' and current_text not in allowed[target]:
        return f'Chỉ có thể trả phòng khi khách đã check-in (trạng thái hiện tại: {current}).'
    return None

def _save_booking_status(booking, status, time_aliases):
    status_field = _booking_status_field(booking)
    if status_field:
        value = _status_value(booking.__class__, (status_field,), status)
        setattr(booking, status_field, value)
    now = timezone.now()
    time_field = _field_name(booking.__class__, *time_aliases)
    if time_field:
        setattr(booking, time_field, now)
    update_fields = []
    if status_field:
        update_fields.append(status_field)
    if time_field:
        update_fields.append(time_field)
    if update_fields:
        booking.save(update_fields=update_fields)
    else:
        raise ValueError('Model đặt phòng không có trường trạng thái hoặc thời gian phù hợp.')

@_receptionist_required
@require_POST
def check_in(request, booking_id):
    try:
        with transaction.atomic():
            booking, error = _get_booking_or_error(booking_id)
            if error:
                return error
            transition_error = _validate_transition(booking, 'check-in')
            if transition_error:
                return JsonResponse({'success': False, 'error': transition_error}, status=400)
            _save_booking_status(booking, 'checked_in', ('check_in_at', 'checkin_at', 'check_in_time', 'actual_check_in'))
            _update_room_status(booking, 'occupied')
        return JsonResponse({'success': True, 'message': 'Check-in thành công.', 'booking_id': booking.pk, 'status': _get_attr(booking, ('status', 'booking_status', 'reservation_status'), 'checked_in')})
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Không thể check-in. Vui lòng kiểm tra dữ liệu đơn đặt phòng.'}, status=500)

@_receptionist_required
@require_POST
def check_out(request, booking_id):
    try:
        with transaction.atomic():
            booking, error = _get_booking_or_error(booking_id)
            if error:
                return error
            transition_error = _validate_transition(booking, 'check-out')
            if transition_error:
                return JsonResponse({'success': False, 'error': transition_error}, status=400)
            _save_booking_status(booking, 'checked_out', ('check_out_at', 'checkout_at', 'check_out_time', 'actual_check_out'))
            _update_room_status(booking, 'available')
        return JsonResponse({'success': True, 'message': 'Check-out thành công.', 'booking_id': booking.pk, 'status': _get_attr(booking, ('status', 'booking_status', 'reservation_status'), 'checked_out')})
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Không thể check-out. Vui lòng kiểm tra dữ liệu đơn đặt phòng.'}, status=500)

@_receptionist_required
@require_POST
def add_service(request, booking_id):
    try:
        service_id = request.POST.get('service_id')
        if not service_id:
            return JsonResponse({'success': False, 'error': 'Thiếu service_id.'}, status=400)
        try:
            quantity = int(request.POST.get('quantity', 1))
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'error': 'quantity phải là số nguyên.'}, status=400)
        if quantity < 1:
            return JsonResponse({'success': False, 'error': 'quantity phải lớn hơn 0.'}, status=400)
        booking_model = _model_by_names('Booking', 'Reservation', 'RoomBooking')
        service_model = _model_by_names('Service', 'HotelService', 'ExtraService')
        if booking_model is None or service_model is None:
            return JsonResponse({'success': False, 'error': 'Chưa tìm thấy model Booking hoặc Service trong dự án.'}, status=501)
        with transaction.atomic():
            booking, error = _get_booking_or_error(booking_id)
            if error:
                return error
            try:
                service = service_model.objects.get(pk=service_id)
            except service_model.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Không tìm thấy dịch vụ.'}, status=404)
            through_model = None
            for field in booking_model._meta.get_fields():
                if getattr(field, 'many_to_many', False) and field.related_model == service_model:
                    through_model = field.remote_field.through
                    break
            if through_model is None:
                through_model = _model_by_names('BookingService', 'ReservationService', 'BookingServiceUsage', 'UsedService')
            if through_model is None or through_model._meta.auto_created:
                return JsonResponse({'success': False, 'error': 'Không tìm thấy bảng liên kết giữa đơn đặt phòng và dịch vụ.'}, status=501)
            booking_fk = next((f for f in through_model._meta.fields if getattr(f, 'many_to_one', False) and f.related_model == booking_model), None)
            service_fk = next((f for f in through_model._meta.fields if getattr(f, 'many_to_one', False) and f.related_model == service_model), None)
            if booking_fk is None or service_fk is None:
                return JsonResponse({'success': False, 'error': 'Model liên kết dịch vụ thiếu khóa ngoại booking/service.'}, status=501)
            price = _get_attr(service, ('price', 'unit_price', 'service_price', 'cost'))
            try:
                unit_price = Decimal(str(price)) if price is not None else Decimal('0')
            except (InvalidOperation, TypeError):
                unit_price = Decimal('0')
            values = {booking_fk.name: booking, service_fk.name: service}
            quantity_field = _field_name(through_model, 'quantity', 'qty', 'amount')
            if quantity_field:
                values[quantity_field] = quantity
            price_field = _field_name(through_model, 'unit_price', 'price', 'service_price')
            if price_field:
                values[price_field] = unit_price
            total_field = _field_name(through_model, 'total_price', 'subtotal', 'total')
            if total_field:
                values[total_field] = unit_price * quantity
            created = through_model.objects.create(**values)
        return JsonResponse({'success': True, 'message': 'Đã thêm dịch vụ vào đơn đặt phòng.', 'booking_id': booking.pk, 'service_id': service.pk, 'quantity': quantity, 'unit_price': str(unit_price), 'total_price': str(unit_price * quantity), 'booking_service_id': created.pk}, status=201)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Không thể thêm dịch vụ. Cần đối chiếu cấu trúc model liên kết dịch vụ.'}, status=500)

@_receptionist_required
@require_POST
def handle_no_show(request, booking_id):
    try:
        with transaction.atomic():
            booking, error = _get_booking_or_error(booking_id)
            if error:
                return error
            transition_error = _validate_transition(booking, 'no-show')
            if transition_error:
                return JsonResponse({'success': False, 'error': transition_error}, status=400)
            _save_booking_status(booking, 'no_show', ('no_show_at', 'noshow_at', 'marked_no_show_at'))
            _update_room_status(booking, 'available')
        return JsonResponse({'success': True, 'message': 'Đã ghi nhận khách không đến (no-show).', 'booking_id': booking.pk, 'status': _get_attr(booking, ('status', 'booking_status', 'reservation_status'), 'no_show')})
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Không thể cập nhật trạng thái no-show.'}, status=500)
