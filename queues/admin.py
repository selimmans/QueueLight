from django.contrib import admin

from .models import QueueEntry, QueueEventLog, PickupEntry, PickupEventLog


@admin.register(QueueEntry)
class QueueEntryAdmin(admin.ModelAdmin):
    list_display = ["name", "business", "status", "position", "batch_number", "joined_at", "called_at"]
    list_filter = ["business", "status"]
    readonly_fields = ["joined_at", "called_at", "intake_answers"]


@admin.register(QueueEventLog)
class QueueEventLogAdmin(admin.ModelAdmin):
    list_display = ["event_type", "business", "entry", "timestamp"]
    list_filter = ["business", "event_type"]
    readonly_fields = ["business", "entry", "event_type", "before_values", "after_values", "timestamp", "meta"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PickupEntry)
class PickupEntryAdmin(admin.ModelAdmin):
    list_display = ["order_number", "business", "customer_name", "status", "registered_at", "ready_at"]
    list_filter = ["business", "status"]
    readonly_fields = ["registered_at", "ready_at", "completed_at"]


@admin.register(PickupEventLog)
class PickupEventLogAdmin(admin.ModelAdmin):
    list_display = ["event_type", "business", "entry", "timestamp"]
    list_filter = ["business", "event_type"]
    readonly_fields = ["business", "entry", "event_type", "timestamp", "meta"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
