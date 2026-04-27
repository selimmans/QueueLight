import pytest
from unittest.mock import patch

from businesses.models import Business
from queues.models import QueueEntry, QueueEventLog
from queues.services import QueueService, RuleViolationError


@pytest.fixture(autouse=True)
def mock_sms():
    with patch("notifications.sms.TwilioSMSBackend.send", return_value=(True, "")):
        yield


@pytest.fixture
def person_business(db):
    return Business.objects.create(
        name="Person Shop",
        slug="person-shop",
        mode=Business.MODE_PERSON,
        is_active=True,
        twilio_from_number="+15005550006",
    )


class TestJoin:
    def test_creates_entry(self, db, active_business):
        entry = QueueService.join(active_business, "Alice", "+16135550200")
        assert entry.pk is not None
        assert entry.status == QueueEntry.Status.WAITING
        assert entry.position == 1
        assert entry.batch_number == 1

    def test_position_increments(self, db, active_business):
        e1 = QueueService.join(active_business, "Alice", "+16135550200")
        e2 = QueueService.join(active_business, "Bob", "+16135550201")
        assert e1.position == 1
        assert e2.position == 2

    def test_batch_fills_before_incrementing(self, db, active_business):
        entries = [
            QueueService.join(active_business, f"C{i}", f"+1613555020{i}")
            for i in range(6)
        ]
        for e in entries[:5]:
            assert e.batch_number == 1
        assert entries[5].batch_number == 2

    def test_rejects_inactive_business(self, db, business):
        with pytest.raises(RuleViolationError, match="not accepting"):
            QueueService.join(business, "Alice", "+16135550200")

    def test_person_mode_no_batch_number(self, db, person_business):
        entry = QueueService.join(person_business, "Alice", "+16135550200")
        assert entry.batch_number is None

    def test_writes_joined_log(self, db, active_business):
        entry = QueueService.join(active_business, "Alice", "+16135550200")
        log = QueueEventLog.objects.get(entry=entry, event_type=QueueEventLog.EventType.JOINED)
        assert log.before_values == {}
        assert log.after_values["status"] == "waiting"
        assert log.meta["mode"] == "batch"


class TestCallNext:
    def test_batch_mode_calls_entire_batch(self, db, batch_entries, active_business):
        QueueService.call_next(active_business)
        for entry in batch_entries:
            entry.refresh_from_db()
            assert entry.status == QueueEntry.Status.CALLED
            assert entry.called_at is not None

    def test_batch_mode_only_calls_lowest_batch(self, db, active_business):
        for i in range(1, 7):
            QueueEntry.objects.create(
                business=active_business,
                name=f"C{i}",
                phone=f"+1613555030{i}",
                status=QueueEntry.Status.WAITING,
                position=i,
                batch_number=1 if i <= 5 else 2,
            )
        QueueService.call_next(active_business)
        assert all(
            e.status == QueueEntry.Status.CALLED
            for e in QueueEntry.objects.filter(business=active_business, batch_number=1)
        )
        assert all(
            e.status == QueueEntry.Status.WAITING
            for e in QueueEntry.objects.filter(business=active_business, batch_number=2)
        )

    def test_person_mode_calls_lowest_position_only(self, db, person_business):
        e1 = QueueEntry.objects.create(
            business=person_business, name="A", phone="+16135550300",
            status=QueueEntry.Status.WAITING, position=1,
        )
        e2 = QueueEntry.objects.create(
            business=person_business, name="B", phone="+16135550301",
            status=QueueEntry.Status.WAITING, position=2,
        )
        QueueService.call_next(person_business)
        e1.refresh_from_db()
        e2.refresh_from_db()
        assert e1.status == QueueEntry.Status.CALLED
        assert e2.status == QueueEntry.Status.WAITING

    def test_empty_queue_raises(self, db, active_business):
        with pytest.raises(RuleViolationError, match="No waiting"):
            QueueService.call_next(active_business)

    def test_writes_called_log_per_entry(self, db, batch_entries, active_business):
        QueueService.call_next(active_business)
        logs = QueueEventLog.objects.filter(
            business=active_business, event_type=QueueEventLog.EventType.CALLED
        )
        assert logs.count() == 5

    def test_returns_called_entries(self, db, batch_entries, active_business):
        result = QueueService.call_next(active_business)
        assert len(result) == 5

    def test_sms_failure_does_not_raise(self, db, batch_entries, active_business):
        with patch("notifications.sms.TwilioSMSBackend.send", return_value=(False, "sms error")):
            result = QueueService.call_next(active_business)
        assert len(result) == 5
        for entry in batch_entries:
            entry.refresh_from_db()
            assert entry.status == QueueEntry.Status.CALLED

    def test_sms_failure_writes_sms_failed_log(self, db, batch_entries, active_business):
        with patch("notifications.sms.TwilioSMSBackend.send", return_value=(False, "sms error")):
            QueueService.call_next(active_business)
        failed = QueueEventLog.objects.filter(
            business=active_business, event_type=QueueEventLog.EventType.SMS_FAILED
        )
        assert failed.count() == 5


class TestAbandon:
    def test_waiting_to_abandoned(self, db, queue_entry):
        QueueService.abandon(queue_entry)
        queue_entry.refresh_from_db()
        assert queue_entry.status == QueueEntry.Status.ABANDONED

    def test_writes_abandoned_log(self, db, queue_entry):
        QueueService.abandon(queue_entry)
        log = QueueEventLog.objects.get(
            entry=queue_entry, event_type=QueueEventLog.EventType.ABANDONED
        )
        assert log.before_values["status"] == "waiting"
        assert log.after_values["status"] == "abandoned"

    def test_abandon_is_for_waiting_not_called(self, db, queue_entry):
        # abandon() is the waiting→abandoned path; no_show() handles called→abandoned
        queue_entry.status = QueueEntry.Status.WAITING
        queue_entry.save()
        QueueService.abandon(queue_entry)
        queue_entry.refresh_from_db()
        assert queue_entry.status == QueueEntry.Status.ABANDONED

    def test_cannot_abandon_completed(self, db, queue_entry):
        queue_entry.status = QueueEntry.Status.COMPLETED
        queue_entry.save()
        with pytest.raises(RuleViolationError):
            QueueService.abandon(queue_entry)

    def test_cannot_abandon_abandoned(self, db, queue_entry):
        queue_entry.status = QueueEntry.Status.ABANDONED
        queue_entry.save()
        with pytest.raises(RuleViolationError):
            QueueService.abandon(queue_entry)


class TestSkip:
    def test_waiting_to_skipped_person_mode(self, db, person_business):
        entry = QueueEntry.objects.create(
            business=person_business, name="A", phone="+16135550400",
            status=QueueEntry.Status.WAITING, position=1,
        )
        QueueService.skip(entry)
        entry.refresh_from_db()
        assert entry.status == QueueEntry.Status.SKIPPED

    def test_writes_skipped_log(self, db, person_business):
        entry = QueueEntry.objects.create(
            business=person_business, name="A", phone="+16135550400",
            status=QueueEntry.Status.WAITING, position=1,
        )
        QueueService.skip(entry)
        log = QueueEventLog.objects.get(
            entry=entry, event_type=QueueEventLog.EventType.SKIPPED
        )
        assert log.before_values["status"] == "waiting"
        assert log.after_values["status"] == "skipped"

    def test_skip_raises_in_batch_mode(self, db, queue_entry):
        with pytest.raises(RuleViolationError, match="batch mode"):
            QueueService.skip(queue_entry)

    def test_cannot_skip_terminal_state(self, db, person_business):
        entry = QueueEntry.objects.create(
            business=person_business, name="A", phone="+16135550400",
            status=QueueEntry.Status.SKIPPED, position=1,
        )
        with pytest.raises(RuleViolationError):
            QueueService.skip(entry)


class TestGuard:
    def test_valid_transition_passes(self, db, queue_entry):
        QueueService._guard(queue_entry, "called")

    def test_invalid_transition_raises(self, db, queue_entry):
        queue_entry.status = QueueEntry.Status.COMPLETED
        with pytest.raises(RuleViolationError):
            QueueService._guard(queue_entry, "called")

    def test_terminal_states_block_all_transitions(self, db, queue_entry):
        for terminal in ("completed", "abandoned", "skipped"):
            queue_entry.status = terminal
            with pytest.raises(RuleViolationError):
                QueueService._guard(queue_entry, "called")
