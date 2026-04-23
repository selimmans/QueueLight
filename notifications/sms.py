# Populated in Phase 4
# Stub present so imports don't fail during Phase 2/3 development.


class TwilioSMSBackend:
    """Thin synchronous wrapper around the Twilio REST API.

    Implemented in Phase 4. This stub ensures the import chain
    works during development of earlier phases.
    """

    def send(self, to: str, body: str, from_: str) -> bool:
        raise NotImplementedError("TwilioSMSBackend not yet implemented — Phase 4")


class SMSTestBackend:
    """Drop-in replacement for TwilioSMSBackend in tests.

    Records sent messages for assertion; never makes real API calls.
    """

    def __init__(self):
        self.sent: list[dict] = []

    def send(self, to: str, body: str, from_: str) -> bool:
        self.sent.append({"to": to, "body": body, "from_": from_})
        return True
