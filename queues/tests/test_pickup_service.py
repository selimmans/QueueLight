from unittest.mock import patch, MagicMock

import pytest

from businesses.models import Business
from queues.models import PickupEntry, PickupEventLog
from queues.pickup_service import PickupService


@pytest.fixture
def pickup_business(db):
    return Business.objects.create(
        name="Pickup Shop",
        slug="pickup-shop",
        is_active=True,
        pickup_enabled=True,
        twilio_from_number="+15005550006",
    )


class TestPickupServiceRegister:
    def test_register_creates_entry(self, pickup_business):
        entry = PickupService.register(pickup_business, order_number="42")
        assert entry.pk is not None
        assert entry.status == PickupEntry.Status.WAITING
        assert entry.order_number == "42"
        assert entry.business == pickup_business

    def test_register_logs_event(self, pickup_business):
        entry = PickupService.register(pickup_business, order_number="42")
        log = PickupEventLog.objects.get(entry=entry, event_type=PickupEventLog.EventType.REGISTERED)
        assert log.business == pickup_business

    def test_register_stores_optional_fields(self, pickup_business):
        entry = PickupService.register(
            pickup_business, order_number="99", customer_name="Alice", phone="+16135550001"
        )
        assert entry.customer_name == "Alice"
        assert entry.phone == "+16135550001"


class TestPickupServiceMarkReady:
    def test_mark_ready_changes_status(self, pickup_business):
        entry = PickupService.register(pickup_business, order_number="7")
        PickupService.mark_ready(entry)
        entry.refresh_from_db()
        assert entry.status == PickupEntry.Status.READY
        assert entry.ready_at is not None

    def test_mark_ready_logs_event(self, pickup_business):
        entry = PickupService.register(pickup_business, order_number="7")
        PickupService.mark_ready(entry)
        assert PickupEventLog.objects.filter(entry=entry, event_type=PickupEventLog.EventType.READY).exists()

    @patch("queues.pickup_service.TwilioSMSBackend.send")
    def test_mark_ready_sends_sms_when_phone_present(self, mock_send, pickup_business):
        mock_send.return_value = (True, "")
        entry = PickupService.register(pickup_business, order_number="7", phone="+16135550001")
        PickupService.mark_ready(entry)
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args
        assert "+16135550001" in str(call_kwargs)

    @patch("queues.pickup_service.TwilioSMSBackend.send")
    def test_mark_ready_skips_sms_when_no_phone(self, mock_send, pickup_business):
        entry = PickupService.register(pickup_business, order_number="7")
        PickupService.mark_ready(entry)
        mock_send.assert_not_called()

    @patch("queues.pickup_service.TwilioSMSBackend.send")
    def test_mark_ready_logs_sms_sent(self, mock_send, pickup_business):
        mock_send.return_value = (True, "")
        entry = PickupService.register(pickup_business, order_number="7", phone="+16135550001")
        PickupService.mark_ready(entry)
        assert PickupEventLog.objects.filter(entry=entry, event_type=PickupEventLog.EventType.SMS_SENT).exists()

    @patch("queues.pickup_service.TwilioSMSBackend.send")
    def test_mark_ready_logs_sms_failed_on_error(self, mock_send, pickup_business):
        mock_send.return_value = (False, "Twilio error")
        entry = PickupService.register(pickup_business, order_number="7", phone="+16135550001")
        PickupService.mark_ready(entry)
        assert PickupEventLog.objects.filter(entry=entry, event_type=PickupEventLog.EventType.SMS_FAILED).exists()

    @patch("queues.pickup_service.TwilioSMSBackend.send")
    def test_sms_uses_custom_message(self, mock_send, pickup_business):
        mock_send.return_value = (True, "")
        pickup_business.pickup_notification_message = "Your order {order_number} is ready at {business_name}!"
        pickup_business.save(update_fields=["pickup_notification_message"])
        entry = PickupService.register(pickup_business, order_number="99", phone="+16135550001")
        PickupService.mark_ready(entry)
        _, call_kwargs = mock_send.call_args
        assert "99" in call_kwargs["body"]
        assert "Pickup Shop" in call_kwargs["body"]

    @patch("queues.pickup_service.TwilioSMSBackend.send")
    def test_sms_uses_default_message_when_blank(self, mock_send, pickup_business):
        mock_send.return_value = (True, "")
        entry = PickupService.register(pickup_business, order_number="55", phone="+16135550001")
        PickupService.mark_ready(entry)
        _, call_kwargs = mock_send.call_args
        assert "55" in call_kwargs["body"]
        assert "Pickup Shop" in call_kwargs["body"]


class TestPickupServiceMarkPickedUp:
    def test_mark_picked_up_changes_status(self, pickup_business):
        entry = PickupService.register(pickup_business, order_number="3")
        PickupService.mark_ready(entry)
        PickupService.mark_picked_up(entry)
        entry.refresh_from_db()
        assert entry.status == PickupEntry.Status.PICKED_UP
        assert entry.completed_at is not None

    def test_mark_picked_up_logs_event(self, pickup_business):
        entry = PickupService.register(pickup_business, order_number="3")
        PickupService.mark_ready(entry)
        PickupService.mark_picked_up(entry)
        assert PickupEventLog.objects.filter(entry=entry, event_type=PickupEventLog.EventType.PICKED_UP).exists()
