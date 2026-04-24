from django.db import transaction
from django.utils import timezone

from queues.models import QueueEntry, QueueEventLog


class RuleViolationError(Exception):
    pass


ALLOWED_TRANSITIONS = {
    "waiting":   {"called", "abandoned", "skipped"},
    "called":    {"completed"},
    "completed": set(),
    "abandoned": set(),
    "skipped":   set(),
}


class QueueService:

    @staticmethod
    def _guard(entry, new_status):
        allowed = ALLOWED_TRANSITIONS.get(entry.status, set())
        if new_status not in allowed:
            raise RuleViolationError(
                f"Cannot transition {entry.status!r} → {new_status!r}."
            )

    @staticmethod
    def _log(business, entry, event_type, before_values, after_values, meta=None):
        QueueEventLog.objects.create(
            business=business,
            entry=entry,
            event_type=event_type,
            before_values=before_values,
            after_values=after_values,
            meta=meta or {},
        )

    @staticmethod
    def join(business, name, phone):
        if not business.is_active:
            raise RuleViolationError("Business is not accepting queue entries.")

        with transaction.atomic():
            entries = QueueEntry.objects.select_for_update().filter(business=business)

            last = entries.order_by("-position").first()
            position = (last.position + 1) if last else 1

            batch_number = None
            if business.mode == business.MODE_BATCH:
                last_batch = entries.order_by("-batch_number").values_list("batch_number", flat=True).first()
                if last_batch is None:
                    batch_number = 1
                else:
                    count_in_batch = entries.filter(batch_number=last_batch).count()
                    batch_number = last_batch if count_in_batch < business.batch_size else last_batch + 1

            entry = QueueEntry.objects.create(
                business=business,
                name=name,
                phone=phone,
                status=QueueEntry.Status.WAITING,
                position=position,
                batch_number=batch_number,
            )

            QueueService._log(
                business=business,
                entry=entry,
                event_type=QueueEventLog.EventType.JOINED,
                before_values={},
                after_values={
                    "status": "waiting",
                    "position": position,
                    "batch_number": batch_number,
                },
                meta={"mode": business.mode, "batch_size": business.batch_size},
            )

        return entry

    @staticmethod
    def call_next(business):
        with transaction.atomic():
            waiting = (
                QueueEntry.objects
                .select_for_update()
                .filter(business=business, status=QueueEntry.Status.WAITING)
                .order_by("position")
            )

            if not waiting.exists():
                raise RuleViolationError("No waiting entries in the queue.")

            if business.mode == business.MODE_BATCH:
                target_batch = (
                    waiting.order_by("batch_number")
                    .values_list("batch_number", flat=True)
                    .first()
                )
                targets = list(waiting.filter(batch_number=target_batch))
            else:
                targets = [waiting.first()]

            now = timezone.now()
            for entry in targets:
                QueueService._guard(entry, "called")
                before = {"status": entry.status}
                entry.status = QueueEntry.Status.CALLED
                entry.called_at = now
                entry.save(update_fields=["status", "called_at"])
                QueueService._log(
                    business=business,
                    entry=entry,
                    event_type=QueueEventLog.EventType.CALLED,
                    before_values=before,
                    after_values={"status": "called", "called_at": now.isoformat()},
                    meta={
                        "mode": business.mode,
                        "batch_size": business.batch_size,
                        "batch_number": entry.batch_number,
                    },
                )

        # SMS sent after atomic block — Twilio calls happen outside the DB lock
        for entry in targets:
            QueueService._send_sms(business, entry)

        return targets

    @staticmethod
    def _send_sms(business, entry):
        from notifications.sms import TwilioSMSBackend
        backend = TwilioSMSBackend()
        body = business.sms_template.format(
            business_name=business.name,
            customer_name=entry.name,
        )
        sent = backend.send(
            to=entry.phone,
            body=body,
            from_=business.twilio_from_number,
        )
        event_type = QueueEventLog.EventType.SMS_SENT if sent else QueueEventLog.EventType.SMS_FAILED
        QueueService._log(
            business=business,
            entry=entry,
            event_type=event_type,
            before_values={},
            after_values={},
            meta={"mode": business.mode},
        )

    @staticmethod
    def abandon(entry):
        business = entry.business
        QueueService._guard(entry, "abandoned")
        before = {"status": entry.status}
        entry.status = QueueEntry.Status.ABANDONED
        entry.save(update_fields=["status"])
        QueueService._log(
            business=business,
            entry=entry,
            event_type=QueueEventLog.EventType.ABANDONED,
            before_values=before,
            after_values={"status": "abandoned"},
            meta={"mode": business.mode, "batch_size": business.batch_size},
        )

    @staticmethod
    def skip(entry):
        business = entry.business
        if business.mode == business.MODE_BATCH:
            raise RuleViolationError("skip() is not allowed in batch mode.")
        QueueService._guard(entry, "skipped")
        before = {"status": entry.status}
        entry.status = QueueEntry.Status.SKIPPED
        entry.save(update_fields=["status"])
        QueueService._log(
            business=business,
            entry=entry,
            event_type=QueueEventLog.EventType.SKIPPED,
            before_values=before,
            after_values={"status": "skipped"},
            meta={"mode": business.mode, "batch_size": business.batch_size},
        )
