import pytest
from django.urls import reverse

from businesses.models import Business
from queues.models import PickupEntry


@pytest.fixture
def queue_only_business(db):
    return Business.objects.create(
        name="Queue Only", slug="queue-only", is_active=True,
        queue_enabled=True, pickup_enabled=False,
    )


@pytest.fixture
def pickup_only_business(db):
    return Business.objects.create(
        name="Pickup Only", slug="pickup-only", is_active=True,
        queue_enabled=False, pickup_enabled=True,
    )


@pytest.fixture
def both_business(db):
    return Business.objects.create(
        name="Both Features", slug="both-features", is_active=True,
        queue_enabled=True, pickup_enabled=True,
    )


@pytest.fixture
def inactive_business(db):
    return Business.objects.create(
        name="Inactive", slug="inactive-biz", is_active=False,
        queue_enabled=False, pickup_enabled=False,
    )


class TestJoinViewModes:
    def test_queue_only_shows_queue_form(self, client, queue_only_business):
        url = reverse("customer:join", kwargs={"slug": queue_only_business.slug})
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"Join the queue" in resp.content
        assert b"panel-pickup" not in resp.content

    def test_pickup_only_shows_pickup_form(self, client, pickup_only_business):
        url = reverse("customer:join", kwargs={"slug": pickup_only_business.slug})
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"order_number" in resp.content
        assert b"Notify me when ready" in resp.content

    def test_both_shows_tab_toggle(self, client, both_business):
        url = reverse("customer:join", kwargs={"slug": both_business.slug})
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"tab-queue" in resp.content
        assert b"tab-pickup" in resp.content

    def test_inactive_shows_inactive_message(self, client, inactive_business):
        url = reverse("customer:join", kwargs={"slug": inactive_business.slug})
        resp = client.get(url)
        assert resp.status_code == 404

    def test_both_disabled_on_active_business(self, client, db):
        biz = Business.objects.create(
            name="Closed", slug="closed-biz", is_active=True,
            queue_enabled=False, pickup_enabled=False,
        )
        url = reverse("customer:join", kwargs={"slug": biz.slug})
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"not currently accepting" in resp.content


class TestPickupJoinView:
    def test_get_shows_form(self, client, pickup_only_business):
        url = reverse("customer:pickup_join", kwargs={"slug": pickup_only_business.slug})
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"order_number" in resp.content

    def test_get_404_when_pickup_disabled(self, client, queue_only_business):
        url = reverse("customer:pickup_join", kwargs={"slug": queue_only_business.slug})
        resp = client.get(url)
        assert resp.status_code == 404

    def test_post_creates_entry_no_phone(self, client, pickup_only_business):
        url = reverse("customer:pickup_join", kwargs={"slug": pickup_only_business.slug})
        resp = client.post(url, {"order_number": "123", "customer_name": "Alice", "phone": ""})
        assert resp.status_code == 302
        entry = PickupEntry.objects.get(business=pickup_only_business, order_number="123")
        assert entry.customer_name == "Alice"
        assert entry.phone == ""

    def test_post_requires_order_number(self, client, pickup_only_business):
        url = reverse("customer:pickup_join", kwargs={"slug": pickup_only_business.slug})
        resp = client.post(url, {"order_number": "", "customer_name": "Alice"})
        assert resp.status_code == 200
        assert b"order number" in resp.content.lower()
        assert PickupEntry.objects.count() == 0

    def test_post_invalid_phone_returns_error(self, client, pickup_only_business):
        url = reverse("customer:pickup_join", kwargs={"slug": pickup_only_business.slug})
        resp = client.post(url, {"order_number": "77", "phone": "not-a-phone"})
        assert resp.status_code == 200
        assert PickupEntry.objects.count() == 0

    def test_post_redirects_to_confirmation(self, client, pickup_only_business):
        url = reverse("customer:pickup_join", kwargs={"slug": pickup_only_business.slug})
        resp = client.post(url, {"order_number": "456"})
        assert resp.status_code == 302
        assert "pickup/confirmation" in resp["Location"]


class TestPickupConfirmView:
    def test_shows_order_number(self, client, pickup_only_business):
        from queues.pickup_service import PickupService
        entry = PickupService.register(pickup_only_business, order_number="789")
        url = reverse("customer:pickup_confirmation", kwargs={
            "slug": pickup_only_business.slug, "entry_id": entry.pk
        })
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"789" in resp.content

    def test_shows_sms_message_when_phone(self, client, pickup_only_business):
        from queues.pickup_service import PickupService
        entry = PickupService.register(pickup_only_business, order_number="999", phone="+16135550001")
        url = reverse("customer:pickup_confirmation", kwargs={
            "slug": pickup_only_business.slug, "entry_id": entry.pk
        })
        resp = client.get(url)
        assert b"text you" in resp.content

    def test_shows_name_message_when_no_phone(self, client, pickup_only_business):
        from queues.pickup_service import PickupService
        entry = PickupService.register(pickup_only_business, order_number="888")
        url = reverse("customer:pickup_confirmation", kwargs={
            "slug": pickup_only_business.slug, "entry_id": entry.pk
        })
        resp = client.get(url)
        assert b"call your name" in resp.content
