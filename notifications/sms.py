import logging

from django.conf import settings
from twilio.rest import Client

logger = logging.getLogger(__name__)


class TwilioSMSBackend:
    def send(self, to: str, body: str, from_: str) -> tuple[bool, str]:
        try:
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            client.messages.create(to=to, from_=from_, body=body)
            return True, ""
        except Exception as exc:
            logger.exception("Twilio SMS send failed to %s", to)
            return False, str(exc)


class SMSTestBackend:
    """Drop-in replacement for TwilioSMSBackend in tests.

    Records sent messages for assertion; never makes real API calls.
    """

    def __init__(self):
        self.sent: list[dict] = []

    def send(self, to: str, body: str, from_: str) -> tuple[bool, str]:
        self.sent.append({"to": to, "body": body, "from_": from_})
        return True, ""
