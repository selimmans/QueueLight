from django.contrib import admin

from .models import Business, StaffPhone


class StaffPhoneInline(admin.TabularInline):
    model = StaffPhone
    extra = 1


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "mode", "batch_size", "is_active", "created_at"]
    list_filter = ["mode", "is_active"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [StaffPhoneInline]


@admin.register(StaffPhone)
class StaffPhoneAdmin(admin.ModelAdmin):
    list_display = ["name", "phone", "business"]
    list_filter = ["business"]
