from django.contrib import admin
from .models import (
    SystemConfig, UserProfile, RoomType, PricingRule,
    Room, Service, Booking, ServiceUsage, Invoice, Review, AuditLog
)

@admin.register(RoomType)
class RoomTypeAdmin(admin.ModelAdmin):
    list_display = ('type_name', 'base_price', 'max_occupancy')
    search_fields = ('type_name',)

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('room_number', 'room_type', 'floor', 'status', 'locked_until')
    list_filter = ('status', 'floor', 'room_type')
    search_fields = ('room_number',)

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('booking_code', 'guest_name', 'room', 'check_in_date', 'check_out_date', 'total_amount', 'booking_status')
    list_filter = ('booking_status', 'check_in_date')
    search_fields = ('booking_code', 'guest_name', 'guest_phone')

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_id', 'booking', 'total_paid', 'payment_method', 'payment_status', 'issue_date')
    list_filter = ('payment_status', 'payment_method')

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('service_name', 'unit_price', 'service_category', 'is_pre_bookable')

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('booking', 'rating', 'created_at', 'manager_reply')

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'ip_address', 'timestamp')
    readonly_fields = ('user', 'action', 'ip_address', 'user_agent', 'timestamp')

# Đăng ký các bảng còn lại
admin.site.register(UserProfile)
admin.site.register(PricingRule)
admin.site.register(ServiceUsage)
admin.site.register(SystemConfig)