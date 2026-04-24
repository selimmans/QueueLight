import pytest

from businesses.models import Business, StaffPhone
from queues.models import QueueEntry


@pytest.fixture
def business(db):
    return Business.objects.create(
        name="Test Salon",
        slug="test-salon",
        mode=Business.MODE_BATCH,
        batch_size=5,
        is_active=False,
    )


@pytest.fixture
def active_business(db):
    return Business.objects.create(
        name="Active Salon",
        slug="active-salon",
        mode=Business.MODE_BATCH,
        batch_size=5,
        is_active=True,
        twilio_from_number="+15005550006",
    )


@pytest.fixture
def staff_phone(db, active_business):
    return StaffPhone.objects.create(
        phone="+16135550001",
        business=active_business,
        name="Staff Member",
    )


@pytest.fixture
def queue_entry(db, active_business):
    return QueueEntry.objects.create(
        business=active_business,
        name="Customer One",
        phone="+16135550100",
        status=QueueEntry.Status.WAITING,
        position=1,
        batch_number=1,
    )


@pytest.fixture
def batch_entries(db, active_business):
    entries = []
    for i in range(1, 6):
        entries.append(
            QueueEntry.objects.create(
                business=active_business,
                name=f"Customer {i}",
                phone=f"+161355501{i:02d}",
                status=QueueEntry.Status.WAITING,
                position=i,
                batch_number=1,
            )
        )
    return entries
