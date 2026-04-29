from django.contrib import admin

from .models import Business, StaffPhone


class StaffPhoneInline(admin.TabularInline):
    model = StaffPhone
    extra = 1


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "business_type", "mode", "queue_enabled", "pickup_enabled", "is_active", "created_at"]
    list_filter = ["business_type", "mode", "is_active", "queue_enabled", "pickup_enabled"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [StaffPhoneInline]
    fieldsets = [
        (None, {"fields": ["name", "slug", "business_type", "is_active", "is_closing", "country"]}),
        ("Branding", {"fields": ["logo_colour", "colour_accent", "colour_border"]}),
        ("Features", {"fields": ["queue_enabled", "pickup_enabled"]}),
        ("Queue", {"fields": ["mode", "batch_size", "avg_service_minutes"]}),
        ("Customer experience", {"fields": ["menu_url", "intake_fields", "sms_template", "pickup_notification_message"]}),
        ("Twilio", {"fields": ["twilio_from_number"]}),
    ]


@admin.register(StaffPhone)
class StaffPhoneAdmin(admin.ModelAdmin):
    list_display = ["name", "phone", "business"]
    list_filter = ["business"]
