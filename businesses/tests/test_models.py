import pytest
from django.db import IntegrityError

from businesses.models import Business, StaffPhone


@pytest.fixture
def business(db):
    return Business.objects.create(name="Test Salon", slug="test-salon", mode="person")


def test_business_str(business):
    assert str(business) == "Test Salon"


def test_business_defaults(business):
    assert business.is_active is False
    assert business.batch_size == 5
    assert business.mode == "person"


def test_business_slug_unique(db, business):
    with pytest.raises(IntegrityError):
        Business.objects.create(name="Dupe", slug="test-salon")


def test_staff_phone_str(db, business):
    sp = StaffPhone.objects.create(phone="+16135550001", business=business, name="Alice")
    assert "Alice" in str(sp)
    assert "+16135550001" in str(sp)


def test_staff_phone_unique_per_business(db, business):
    StaffPhone.objects.create(phone="+16135550001", business=business, name="Alice")
    with pytest.raises(IntegrityError):
        StaffPhone.objects.create(phone="+16135550001", business=business, name="Alice Dupe")


def test_staff_phone_same_number_different_business(db, business):
    other = Business.objects.create(name="Other", slug="other", mode="batch")
    StaffPhone.objects.create(phone="+16135550001", business=business, name="Alice")
    sp2 = StaffPhone.objects.create(phone="+16135550001", business=other, name="Bob")
    assert sp2.pk is not None
