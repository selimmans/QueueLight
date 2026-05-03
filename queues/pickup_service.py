import logging
from django.conf import settings
from django.utils import timezone

from businesses.models import Business
from notifications.sms import TwilioSMSBackend
from .models import PickupEntry, PickupEventLog

logger = logging.getLogger(__name__)


class PickupService:
    @staticmethod
    def register(business: Business, order_number: str, customer_name: str = "", phone: str = "", intake_answers: dict | None = None) -> PickupEntry:
        entry = PickupEntry.objects.create(
            business=business,
            order_number=order_number,
            customer_name=customer_name,
            phone=phone,
            status=PickupEntry.Status.WAITING,
            intake_answers=intake_answers or {},
        )
        PickupEventLog.objects.create(
            business=business,
            entry=entry,
            event_type=PickupEventLog.EventType.REGISTERED,
            meta={"order_number": order_number},
        )
        return entry

    @staticmethod
    def mark_ready(entry: PickupEntry) -> PickupEntry:
        entry.status = PickupEntry.Status.READY
        entry.ready_at = timezone.now()
        entry.save(update_fields=["status", "ready_at"])

        PickupEventLog.objects.create(
            business=entry.business,
            entry=entry,
            event_type=PickupEventLog.EventType.READY,
            meta={"order_number": entry.order_number},
        )

        if entry.phone:
            PickupService._send_ready_sms(entry)

        return entry

    @staticmethod
    def mark_picked_up(entry: PickupEntry) -> PickupEntry:
        entry.status = PickupEntry.Status.PICKED_UP
        entry.completed_at = timezone.now()
        entry.save(update_fields=["status", "completed_at"])

        PickupEventLog.objects.create(
            business=entry.business,
            entry=entry,
            event_type=PickupEventLog.EventType.PICKED_UP,
            meta={"order_number": entry.order_number},
        )
        return entry

    CLOSING_SOON_DEFAULT = "{business_name} is closing soon — please come pick up your order as soon as possible."

    @staticmethod
    def clear_active_orders(business: Business) -> int:
        """Cancel all waiting and ready pickup entries. Returns count cleared."""
        count = PickupEntry.objects.filter(
            business=business,
            status__in=[PickupEntry.Status.WAITING, PickupEntry.Status.READY],
        ).update(status=PickupEntry.Status.CANCELLED)
        if count:
            PickupEventLog.objects.create(
                business=business,
                event_type=PickupEventLog.EventType.CANCELLED,
                meta={"cleared_count": count},
            )
        return count

    @staticmethod
    def send_closing_soon_sms(business: Business) -> tuple[int, int]:
        """Send closing-soon SMS to all active customers with a phone number.
        Returns (sent_count, failed_count)."""
        active = PickupEntry.objects.filter(
            business=business,
            status__in=[PickupEntry.Status.WAITING, PickupEntry.Status.READY],
            phone__gt="",
        )
        sent, failed = 0, 0
        for entry in active:
            PickupService._send_closing_soon_sms_to(entry)
            # Check the last log to see if it succeeded
            last = PickupEventLog.objects.filter(
                entry=entry, event_type__in=[
                    PickupEventLog.EventType.SMS_SENT,
                    PickupEventLog.EventType.SMS_FAILED,
                ]
            ).order_by("-timestamp").first()
            if last and last.event_type == PickupEventLog.EventType.SMS_SENT:
                sent += 1
            else:
                failed += 1
        return sent, failed

    @staticmethod
    def _send_closing_soon_sms_to(entry: PickupEntry):
        business = entry.business
        from_number = business.twilio_from_number or getattr(settings, "TWILIO_FROM_NUMBER", "")
        if not from_number:
            return
        template = PickupService.CLOSING_SOON_DEFAULT
        body = template.format(business_name=business.name)
        backend = TwilioSMSBackend()
        success, error = backend.send(to=entry.phone, body=body, from_=from_number)
        event_type = PickupEventLog.EventType.CLOSING_SOON_SMS if success else PickupEventLog.EventType.SMS_FAILED
        PickupEventLog.objects.create(
            business=business,
            entry=entry,
            event_type=event_type,
            meta={"to": entry.phone, "error": error},
        )

    @staticmethod
    def _send_ready_sms(entry: PickupEntry):
        business = entry.business
        from_number = business.twilio_from_number or getattr(settings, "TWILIO_FROM_NUMBER", "")
        if not from_number:
            logger.warning("No Twilio from number configured for business %s", business.slug)
            return

        template = business.pickup_notification_message or business.PICKUP_NOTIFICATION_DEFAULT
        body = template.format(
            business_name=business.name,
            order_number=entry.order_number,
            customer_name=entry.customer_name or "",
        )

        backend = TwilioSMSBackend()
        success, error = backend.send(to=entry.phone, body=body, from_=from_number)

        event_type = PickupEventLog.EventType.SMS_SENT if success else PickupEventLog.EventType.SMS_FAILED
        PickupEventLog.objects.create(
            business=business,
            entry=entry,
            event_type=event_type,
            meta={"to": entry.phone, "error": error},
        )
