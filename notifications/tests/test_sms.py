from unittest.mock import MagicMock, patch

import pytest

from notifications.sms import SMSTestBackend, TwilioSMSBackend
from queues.models import QueueEventLog
from queues.services import QueueService


class TestTwilioSMSBackend:
    @patch("notifications.sms.Client")
    def test_send_calls_twilio_with_correct_args(self, MockClient):
        mock_client = MagicMock()
        MockClient.return_value = mock_client

        backend = TwilioSMSBackend()
        result = backend.send(to="+16135550100", body="Hello", from_="+15005550006")

        assert result is True
        mock_client.messages.create.assert_called_once_with(
            to="+16135550100",
            from_="+15005550006",
            body="Hello",
        )

    @patch("notifications.sms.Client")
    def test_send_returns_false_on_twilio_exception(self, MockClient):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("Twilio error")
        MockClient.return_value = mock_client

        backend = TwilioSMSBackend()
        result = backend.send(to="+16135550100", body="Hello", from_="+15005550006")

        assert result is False

    @patch("notifications.sms.Client")
    def test_send_does_not_raise_on_twilio_exception(self, MockClient):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("network failure")
        MockClient.return_value = mock_client

        backend = TwilioSMSBackend()
        try:
            backend.send(to="+16135550100", body="Hello", from_="+15005550006")
        except Exception:
            pytest.fail("TwilioSMSBackend.send() raised an exception to the caller")


class TestSMSTestBackend:
    def test_send_records_message(self):
        backend = SMSTestBackend()
        backend.send(to="+16135550100", body="Hello", from_="+15005550006")
        assert backend.sent == [{"to": "+16135550100", "body": "Hello", "from_": "+15005550006"}]

    def test_send_returns_true(self):
        backend = SMSTestBackend()
        assert backend.send(to="+1", body="x", from_="+2") is True


class TestCallNextWithSMSFailure:
    @patch("notifications.sms.TwilioSMSBackend.send", return_value=False)
    def test_call_next_completes_when_sms_fails(self, mock_send, db, active_business, queue_entry):
        targets = QueueService.call_next(active_business)

        assert len(targets) == 1
        queue_entry.refresh_from_db()
        assert queue_entry.status == "called"

    @patch("notifications.sms.TwilioSMSBackend.send", return_value=False)
    def test_sms_failed_is_logged_when_send_returns_false(self, mock_send, db, active_business, queue_entry):
        QueueService.call_next(active_business)

        assert QueueEventLog.objects.filter(
            business=active_business,
            entry=queue_entry,
            event_type=QueueEventLog.EventType.SMS_FAILED,
        ).exists()

    def test_call_next_completes_with_sms_test_backend(self, db, active_business, queue_entry):
        backend = SMSTestBackend()
        with patch("notifications.sms.TwilioSMSBackend", return_value=backend):
            targets = QueueService.call_next(active_business)

        assert len(targets) == 1
        assert len(backend.sent) == 1
        assert backend.sent[0]["to"] == queue_entry.phone
