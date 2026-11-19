from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import uuid

# 1. BẢNG CẤU HÌNH HỆ THỐNG (SYSTEM_CONFIGS) - UC-33
class SystemConfig(models.Model):
    config_key = models.CharField(max_length=50, primary_key=True, verbose_name="Tên tham số (PK)")
    config_value = models.TextField(verbose_name="Giá trị cấu hình")
    description = models.CharField(max_length=255, blank=True, verbose_name="Mô tả tham số")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời gian cập nhật")

    class Meta:
        verbose_name = "Cấu hình hệ thống"
        verbose_name_plural = "Cấu hình hệ thống"

    def __str__(self):
        return f"{self.config_key}: {self.config_value}"



# 2. BẢNG NGƯỜI DÙNG & PHÂN QUYỀN RBAC (USERS)
class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('CUSTOMER', 'Khách hàng'),
        ('RECEPTIONIST', 'Lễ tân'),
        ('MANAGER', 'Quản lý'),
        ('ADMIN', 'Quản trị viên'),
    ]
    STATUS_CHOICES = [
        ('ACTIVE', 'Hoạt động'),
        ('LOCKED', 'Đã khóa'),
        ('DEACTIVATED', 'Đã nghỉ việc / Vô hiệu hóa'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile', primary_key=True)
    phone = models.CharField(max_length=20, blank=True, verbose_name="Số điện thoại")
    avatar_url = models.CharField(max_length=255, blank=True, null=True, verbose_name="Link ảnh đại diện")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='CUSTOMER', verbose_name="Vai trò")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE', verbose_name="Trạng thái")
    identity_card_encrypted = models.CharField(max_length=255, blank=True, null=True, verbose_name="CCCD mã hóa AES-256")
    shift_code = models.CharField(max_length=50, blank=True, null=True, verbose_name="Ca làm việc")
    department = models.CharField(max_length=100, blank=True, null=True, verbose_name="Phòng ban")
    failed_login_attempts = models.IntegerField(default=0, verbose_name="Số lần đăng nhập sai")
    locked_until = models.DateTimeField(null=True, blank=True, verbose_name="Khóa đến thời điểm")
    is_anonymized = models.BooleanField(default=False, verbose_name="Đã xóa danh tính (NĐ 13/2023)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Ngày tạo tài khoản")

    class Meta:
        verbose_name = "Hồ sơ người dùng"
        verbose_name_plural = "Danh sách người dùng"

    def __str__(self):
        return f"[{self.role}] {self.user.username} - {self.user.get_full_name()}"


# 3. BẢNG LOẠI PHÒNG (ROOM_TYPES)
class RoomType(models.Model):
    type_id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4, verbose_name="Mã loại phòng (PK)")
    type_name = models.CharField(max_length=50, unique=True, verbose_name="Tên loại phòng (UK)")
    base_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Giá cơ bản / đêm (VNĐ)")
    max_occupancy = models.IntegerField(default=2, verbose_name="Số khách tối đa")
    description = models.TextField(blank=True, verbose_name="Mô tả chi tiết")

    class Meta:
        verbose_name = "Loại phòng"
        verbose_name_plural = "Danh mục loại phòng"

    def __str__(self):
        return f"{self.type_name} ({self.base_price:,.0f} đ/đêm)"


# 4. BẢNG QUY TẮC GIÁ LINH HOẠT (PRICING_RULES) - UC-26
class PricingRule(models.Model):
    RATE_TYPE_CHOICES = [
        ('WEEKEND', 'Cuối tuần'),
        ('SEASONAL', 'Mùa cao điểm'),
        ('HOLIDAY', 'Lễ tết'),
        ('PROMO', 'Khuyến mại'),
    ]
    rule_id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4, verbose_name="Mã quy tắc (PK)")
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name='pricing_rules', verbose_name="Loại phòng áp dụng (FK)")
    rate_type = models.CharField(max_length=20, choices=RATE_TYPE_CHOICES, verbose_name="Loại giá áp dụng")
    start_date = models.DateField(verbose_name="Ngày bắt đầu")
    end_date = models.DateField(verbose_name="Ngày kết thúc")
    price_or_percent = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Giá trị tiền hoặc %")
    is_percentage = models.BooleanField(default=False, verbose_name="Tính theo phần trăm")

    class Meta:
        verbose_name = "Quy tắc giá"
        verbose_name_plural = "Bảng giá linh hoạt"


# 5. BẢNG PHÒNG VẬT LÝ (ROOMS) - UC-24, UC-25, UI-06
# 
class Room(models.Model):
    STATUS_CHOICES = [
        ('AVAILABLE', 'Còn trống (Sẵn sàng)'),   # Xanh lá #16A34A
        ('RESERVED', 'Đã đặt trước'),            # Xanh dương #2563EB
        ('OCCUPIED', 'Có khách đang ở'),         # Đỏ #DC2626
        ('CLEANING', 'Đang dọn dẹp'),            # Vàng #EAB308
        ('MAINTENANCE', 'Bảo trì / Tạm ngưng'),  # Xám #6B7280
    ]
    room_id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4, verbose_name="Mã phòng (PK)")
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name='rooms', verbose_name="Loại phòng (FK)")
    room_number = models.CharField(max_length=10, unique=True, verbose_name="Số phòng (UK)")
    floor = models.IntegerField(default=1, verbose_name="Tầng")
    area = models.FloatField(default=35.0, verbose_name="Diện tích (m2)")
    capacity = models.IntegerField(default=2, verbose_name="Sức chứa tối đa")
    amenities = models.JSONField(default=list, blank=True, verbose_name="Tiện ích phòng (JSON)")
    images = models.JSONField(default=list, blank=True, verbose_name="Bộ ảnh thực tế (JSON)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='AVAILABLE', verbose_name="Trạng thái phòng")
    locked_until = models.DateTimeField(null=True, blank=True, verbose_name="Thời gian giữ phòng tạm thời (10p)")

    class Meta:
        verbose_name = "Phòng"
        verbose_name_plural = "Danh sách phòng"

    def is_locked(self):
        """Kiểm tra xem phòng có đang bị khóa giữ chỗ thanh toán 10 phút hay không (UC-07)"""
        if self.locked_until and self.locked_until > timezone.now():
            return True
        return False

    def __str__(self):
        return f"Phòng {self.room_number} - Tầng {self.floor} ({self.room_type.type_name})"


# 
# 6. BẢNG NHẬT KÝ BẢO MẬT HỆ THỐNG (AUDIT_LOGS) - UC-34
class AuditLog(models.Model):
    log_id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4, verbose_name="Mã log (PK)")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs', verbose_name="Người thực hiện (FK)")
    action = models.CharField(max_length=255, verbose_name="Hành động thao tác")
    ip_address = models.CharField(max_length=45, blank=True, verbose_name="Địa chỉ IP")
    user_agent = models.TextField(blank=True, verbose_name="Thông tin trình duyệt / Thiết bị")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm ghi log")

    class Meta:
        verbose_name = "Nhật ký hệ thống"
        verbose_name_plural = "Nhật ký bảo mật (Audit Logs)"


#
# 7. BẢNG ĐƠN ĐẶT PHÒNG (BOOKINGS) - UC-07, UC-11, UC-18, UC-20
class Booking(models.Model):
    STATUS_CHOICES = [
        ('PENDING_PAYMENT', 'Chờ thanh toán (Giữ 10p)'),
        ('PENDING_APPROVAL', 'Chờ duyệt (Thanh toán tại KS)'),
        ('CONFIRMED', 'Đã xác nhận'),
        ('STAYING', 'Đang lưu trú (Đã Check-in)'),
        ('COMPLETED', 'Đã hoàn tất (Đã Check-out)'),
        ('CANCELLED', 'Đã hủy'),
        ('NO_SHOW', 'Khách không đến (No-show)'),
    ]
    booking_id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4, verbose_name="Mã đơn (PK)")
    booking_code = models.CharField(max_length=15, unique=True, editable=False, verbose_name="Mã hiển thị (BK-XXXXXX)")
    customer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings', verbose_name="Khách hàng (FK)")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='bookings', verbose_name="Phòng đặt (FK)")
    
    guest_name = models.CharField(max_length=100, verbose_name="Họ tên khách")
    guest_phone = models.CharField(max_length=20, verbose_name="Số điện thoại")
    guest_email = models.EmailField(verbose_name="Email nhận xác nhận")
    guest_id_card = models.CharField(max_length=50, blank=True, null=True, verbose_name="Số CCCD / Hộ chiếu")

    check_in_date = models.DateTimeField(verbose_name="Ngày nhận phòng")
    check_out_date = models.DateTimeField(verbose_name="Ngày trả phòng")
    actual_check_in = models.DateTimeField(null=True, blank=True, verbose_name="Thời điểm Check-in thực tế")
    actual_check_out = models.DateTimeField(null=True, blank=True, verbose_name="Thời điểm Check-out thực tế")
    num_of_guests = models.IntegerField(default=1, verbose_name="Số lượng khách")
    special_requests = models.TextField(blank=True, null=True, verbose_name="Yêu cầu đặc biệt")
    
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Tổng tiền thanh toán (VNĐ)")
    booking_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING_PAYMENT', verbose_name="Trạng thái đơn")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm tạo đơn")

    class Meta:
        verbose_name = "Đơn đặt phòng"
        verbose_name_plural = "Danh sách đơn đặt phòng"

    def save(self, *args, **kwargs):
        """Tự động sinh mã hiển thị BK-XXXXXX ngẫu nhiên duy nhất khi tạo mới"""
        if not self.booking_code:
            self.booking_code = f"BK-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    def calculate_cancellation_refund(self):
        """
        Thuật toán tính toán số tiền hoàn và phí phạt theo đúng mốc thời gian UC-11:
        - Hủy trước > 72h: Hoàn 100%, phạt 0 VNĐ.
        - Hủy từ 24h - 72h: Phạt phí đêm đầu tiên, hoàn lại phần còn lại.
        - Hủy dưới < 24h: Phạt 100%, không hoàn tiền.
        """
        now = timezone.now()
        check_in_time = self.check_in_date
        time_diff = check_in_time - now

        if time_diff > timedelta(hours=72):
            return self.total_amount, 0
        elif timedelta(hours=24) <= time_diff <= timedelta(hours=72):
            first_night_fee = self.room.room_type.base_price
            refund = max(0, self.total_amount - first_night_fee)
            return refund, first_night_fee
        else:
            return 0, self.total_amount

    def __str__(self):
        return f"[{self.booking_code}] {self.guest_name} - Phòng {self.room.room_number}"


# 8. BẢNG DANH MỤC DỊCH VỤ PHỤ TRỢ (SERVICES) - UC-27
class Service(models.Model):
    CATEGORY_CHOICES = [
        ('MINIBAR', 'Đồ uống Minibar'),
        ('LAUNDRY', 'Giặt là'),
        ('SPA', 'Spa & Massage'),
        ('TRANSPORT', 'Xe đưa đón sân bay'),
        ('EXTRA_BED', 'Kê thêm giường phụ'),
        ('SURCHARGE', 'Phụ thu Check-in sớm / Check-out muộn'),
    ]
    service_id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4, verbose_name="Mã dịch vụ (PK)")
    service_name = models.CharField(max_length=100, verbose_name="Tên dịch vụ")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Đơn giá niêm yết (VNĐ)")
    is_pre_bookable = models.BooleanField(default=False, verbose_name="Cho phép khách đặt trước online")
    service_category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='MINIBAR', verbose_name="Phân loại dịch vụ")

    class Meta:
        verbose_name = "Dịch vụ phụ trợ"
        verbose_name_plural = "Danh mục dịch vụ & Phụ phí"

    def __str__(self):
        return f"{self.service_name} ({self.unit_price:,.0f} đ)"


# 9. BẢNG CHI TIẾT SỬ DỤNG DỊCH VỤ (SERVICE_USAGES) - UC-19
class ServiceUsage(models.Model):
    usage_id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4, verbose_name="Mã sử dụng (PK)")
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='services_used', verbose_name="Đơn đặt phòng (FK)")
    service = models.ForeignKey(Service, on_delete=models.CASCADE, verbose_name="Dịch vụ sử dụng (FK)")
    quantity = models.IntegerField(default=1, verbose_name="Số lượng")
    unit_price_at_use = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Đơn giá tại thời điểm dùng")
    used_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm ghi nhận")
    sub_total = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Thành tiền (VNĐ)")

    class Meta:
        verbose_name = "Dịch vụ phát sinh"
        verbose_name_plural = "Bảng chi tiết sử dụng dịch vụ"

    def save(self, *args, **kwargs):
        self.sub_total = self.quantity * self.unit_price_at_use
        super().save(*args, **kwargs)


# 10. BẢNG HÓA ĐƠN ĐIỆN TỬ (INVOICES) - UC-13, TT 78/2021/TT-BTC
class Invoice(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('CARD', 'Thẻ quốc tế (Visa/Mastercard/JCB)'),
        ('E_WALLET', 'Ví điện tử / QR (VNPay/MoMo/ZaloPay)'),
        ('PAY_AT_HOTEL', 'Thanh toán tại khách sạn'),
    ]
    PAYMENT_STATUS_CHOICES = [
        ('PENDING', 'Chờ thanh toán'),
        ('PAID', 'Đã thanh toán đủ'),
        ('REFUNDED', 'Đã hoàn tiền'),
    ]
    invoice_id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4, verbose_name="Mã hóa đơn (PK)")
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='invoice', verbose_name="Đơn đặt phòng (FK, UK)")
    issue_date = models.DateTimeField(auto_now_add=True, verbose_name="Ngày phát hành hóa đơn")
    room_charge = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Tiền phòng")
    service_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Tiền dịch vụ phụ trợ")
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Thuế GTGT 10% VAT")
    total_paid = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Tổng tiền thanh toán")
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Số tiền đã hoàn lại")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, verbose_name="Phương thức thanh toán")
    transaction_code = models.CharField(max_length=100, blank=True, verbose_name="Mã giao dịch cổng thanh toán")
    idempotency_key = models.CharField(max_length=100, unique=True, verbose_name="Khóa chống trùng giao dịch (UK)")
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='PAID', verbose_name="Trạng thái hóa đơn")
    pdf_url = models.CharField(max_length=255, blank=True, verbose_name="Đường dẫn file hóa đơn PDF")

    class Meta:
        verbose_name = "Hóa đơn điện tử"
        verbose_name_plural = "Danh sách hóa đơn (Invoices)"


# 11. BẢNG ĐÁNH GIÁ & PHẢN HỒI (REVIEWS) - UC-14, UC-31
class Review(models.Model):
    review_id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4, verbose_name="Mã đánh giá (PK)")
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='review', verbose_name="Đơn đặt phòng (FK, UK)")
    rating = models.IntegerField(default=5, verbose_name="Số sao đánh giá (1-5)")
    comment = models.TextField(verbose_name="Bình luận nhận xét (Tối thiểu 10 ký tự)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm đánh giá")
    manager_reply = models.TextField(blank=True, null=True, verbose_name="Phản hồi từ Khách sạn (UC-31)")
    replied_at = models.DateTimeField(blank=True, null=True, verbose_name="Thời điểm phản hồi")

    class Meta:
        verbose_name = "Đánh giá phòng"
        verbose_name_plural = "Đánh giá & Phản hồi"

    def __str__(self):
        return f"[{self.rating}★] {self.booking.guest_name} - Phòng {self.booking.room.room_number}"