import pytest

from businesses.models import Business
from queues.models import QueueEntry, QueueEventLog


@pytest.fixture
def business(db):
    return Business.objects.create(name="Test Salon", slug="test-salon", mode="batch", batch_size=3)


def test_queue_entry_defaults(db, business):
    entry = QueueEntry.objects.create(
        business=business,
        name="Jane",
        phone="+16135550002",
        position=1,
    )
    assert entry.status == QueueEntry.Status.WAITING
    assert entry.batch_number is None
    assert entry.called_at is None
    assert entry.joined_at is not None


def test_queue_entry_str(db, business):
    entry = QueueEntry.objects.create(
        business=business, name="Jane", phone="+16135550002", position=1
    )
    assert "Jane" in str(entry)
    assert "test-salon" in str(entry)


def test_queue_entry_ordering(db, business):
    QueueEntry.objects.create(business=business, name="B", phone="+16135550003", position=2)
    QueueEntry.objects.create(business=business, name="A", phone="+16135550002", position=1)
    entries = list(QueueEntry.objects.filter(business=business))
    assert entries[0].position == 1
    assert entries[1].position == 2


def test_queue_event_log_insert(db, business):
    entry = QueueEntry.objects.create(
        business=business, name="Jane", phone="+16135550002", position=1
    )
    log = QueueEventLog.objects.create(
        business=business,
        entry=entry,
        event_type=QueueEventLog.EventType.JOINED,
        before_values={},
        after_values={"status": "waiting"},
        meta={"mode": "batch", "batch_size": 3},
    )
    assert log.pk is not None
    assert log.timestamp is not None


def test_queue_event_log_entry_nullable(db, business):
    log = QueueEventLog.objects.create(
        business=business,
        entry=None,
        event_type=QueueEventLog.EventType.CALLED,
        meta={},
    )
    assert log.entry is None
