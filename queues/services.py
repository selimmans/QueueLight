from django.db import transaction
from django.utils import timezone

from queues.models import QueueEntry, QueueEventLog


class RuleViolationError(Exception):
    pass


ALLOWED_TRANSITIONS = {
    "waiting":   {"called", "abandoned", "skipped"},
    "called":    {"completed", "abandoned"},
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
    def join(business, name, phone, intake_answers=None):
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
                intake_answers=intake_answers or {},
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
        from django.conf import settings as django_settings
        from notifications.sms import TwilioSMSBackend
        backend = TwilioSMSBackend()
        body = business.sms_template.format(
            business_name=business.name,
            customer_name=entry.name,
        )
        from_number = business.twilio_from_number or django_settings.TWILIO_FROM_NUMBER
        sent, error = backend.send(
            to=entry.phone,
            body=body,
            from_=from_number,
        )
        event_type = QueueEventLog.EventType.SMS_SENT if sent else QueueEventLog.EventType.SMS_FAILED
        meta = {"mode": business.mode}
        if error:
            meta["sms_error"] = error
        QueueService._log(
            business=business,
            entry=entry,
            event_type=event_type,
            before_values={},
            after_values={},
            meta=meta,
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
    def complete(entry):
        business = entry.business
        QueueService._guard(entry, "completed")
        before = {"status": entry.status}
        entry.status = QueueEntry.Status.COMPLETED
        entry.save(update_fields=["status"])
        QueueService._log(
            business=business,
            entry=entry,
            event_type=QueueEventLog.EventType.COMPLETED,
            before_values=before,
            after_values={"status": "completed"},
            meta={"mode": business.mode, "batch_size": business.batch_size},
        )

    @staticmethod
    def no_show(entry):
        """Mark a called entry as abandoned (no-show)."""
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
            meta={"mode": business.mode, "batch_size": business.batch_size, "reason": "no_show"},
        )

    @staticmethod
    def complete_batch(business, showed_up: int):
        """Settle currently-called batch then call the next one.

        showed_up: how many entries to mark completed (rest → abandoned).
        """
        with transaction.atomic():
            called = list(
                QueueEntry.objects.select_for_update()
                .filter(business=business, status=QueueEntry.Status.CALLED)
                .order_by("position")
            )

            if not called:
                raise RuleViolationError("No called entries to settle.")

            showed_up = max(0, min(showed_up, len(called)))

            for i, entry in enumerate(called):
                if i < showed_up:
                    QueueService._guard(entry, "completed")
                    before = {"status": entry.status}
                    entry.status = QueueEntry.Status.COMPLETED
                    entry.save(update_fields=["status"])
                    QueueService._log(
                        business=business,
                        entry=entry,
                        event_type=QueueEventLog.EventType.COMPLETED,
                        before_values=before,
                        after_values={"status": "completed"},
                        meta={"mode": business.mode, "showed_up": showed_up, "batch_total": len(called)},
                    )
                else:
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
                        meta={"mode": business.mode, "showed_up": showed_up, "batch_total": len(called), "reason": "no_show"},
                    )

        # Call next batch outside the atomic block
        try:
            QueueService.call_next(business)
        except RuleViolationError:
            pass  # Queue empty — settlement still succeeded

    @staticmethod
    def clear_queue(business):
        """Mark all WAITING entries as abandoned. Logs one QUEUE_CLEARED event."""
        with transaction.atomic():
            waiting = list(
                QueueEntry.objects.select_for_update()
                .filter(business=business, status=QueueEntry.Status.WAITING)
            )
            for entry in waiting:
                entry.status = QueueEntry.Status.ABANDONED
                entry.save(update_fields=["status"])

            QueueEventLog.objects.create(
                business=business,
                entry=None,
                event_type=QueueEventLog.EventType.QUEUE_CLEARED,
                before_values={"cleared_count": len(waiting)},
                after_values={},
                meta={"mode": business.mode},
            )

    @staticmethod
    def send_closing_soon_sms(business):
        """Send a closing-soon SMS to all WAITING entries and set is_closing."""
        waiting = list(
            QueueEntry.objects.filter(business=business, status=QueueEntry.Status.WAITING)
        )
        business.is_closing = True
        business.save(update_fields=["is_closing"])

        from django.conf import settings as django_settings
        from notifications.sms import TwilioSMSBackend
        backend = TwilioSMSBackend()
        body = f"{business.name} is closing soon — you may not be served today. Sorry for the inconvenience."
        from_number = business.twilio_from_number or django_settings.TWILIO_FROM_NUMBER
        for entry in waiting:
            sent, error = backend.send(to=entry.phone, body=body, from_=from_number)
            event_type = (
                QueueEventLog.EventType.CLOSING_SOON_SMS if sent
                else QueueEventLog.EventType.SMS_FAILED
            )
            meta = {"mode": business.mode}
            if error:
                meta["sms_error"] = error
            QueueEventLog.objects.create(
                business=business,
                entry=entry,
                event_type=event_type,
                before_values={},
                after_values={},
                meta=meta,
            )

    @staticmethod
    def set_mode(business, new_mode):
        """Switch business mode. Only allowed when queue has no non-terminal entries."""
        active = QueueEntry.objects.filter(
            business=business,
            status__in=[QueueEntry.Status.WAITING, QueueEntry.Status.CALLED],
        ).exists()
        if active:
            raise RuleViolationError("Cannot change mode while the queue has active entries.")
        business.mode = new_mode
        business.save(update_fields=["mode"])

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
