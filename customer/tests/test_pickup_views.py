import json

import pytest
from django.urls import reverse

from businesses.models import Business
from queues.models import PickupEntry
from queues.pickup_service import PickupService


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


@pytest.fixture
def kotn_business(db):
    return Business.objects.create(
        name="Kotn Cup 26 Toronto", slug="kotn-cup-toronto", is_active=True,
        queue_enabled=False, pickup_enabled=True,
    )


def _kotn_shirt(name="ALI", patch="sporting-club", placement="left-arm"):
    return {
        "patches": [{"key": patch, "placement": placement}],
        "sleeve": "short-sleeve",
        "size": "m",
        "name": name,
    }


class TestKotnTagNumbering:
    def test_first_order_starts_at_001(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        resp = client.post(url, {"phone": "+16135550100", "shirts": json.dumps([_kotn_shirt()])})
        assert resp.status_code == 302
        entry = PickupEntry.objects.get(business=kotn_business)
        assert entry.intake_answers["Shirts"][0]["tag"] == "001"

    def test_second_order_continues_numbering(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        client.post(url, {"phone": "+16135550100", "shirts": json.dumps([_kotn_shirt("ALI")])})
        resp = client.post(url, {"phone": "+16135550101", "shirts": json.dumps([_kotn_shirt("BOB")])})
        assert resp.status_code == 302
        entry = PickupEntry.objects.get(intake_answers__Shirts__0__name="BOB")
        assert entry.intake_answers["Shirts"][0]["tag"] == "002"

    def test_reset_restarts_numbering_at_001(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        client.post(url, {"phone": "+16135550100", "shirts": json.dumps([_kotn_shirt("ALI")])})
        client.post(url, {"phone": "+16135550101", "shirts": json.dumps([_kotn_shirt("BOB")])})

        PickupService.reset_tag_numbering(kotn_business)

        resp = client.post(url, {"phone": "+16135550102", "shirts": json.dumps([_kotn_shirt("CAT")])})
        assert resp.status_code == 302
        entry = PickupEntry.objects.get(intake_answers__Shirts__0__name="CAT")
        assert entry.intake_answers["Shirts"][0]["tag"] == "001"
        # Past orders are untouched — still on record with their original tags.
        assert PickupEntry.objects.count() == 3


class TestKotnNameOptional:
    """Name-sticking supplies ran out — the form no longer collects a name,
    so a blank/missing name must succeed and default to "NO NAME" instead
    of being rejected."""

    def test_blank_name_defaults_and_succeeds(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        resp = client.post(url, {"phone": "+16135550100", "shirts": json.dumps([_kotn_shirt(name="")])})
        assert resp.status_code == 302
        entry = PickupEntry.objects.get(business=kotn_business)
        assert entry.intake_answers["Shirts"][0]["name"] == "NO NAME"

    def test_missing_name_key_defaults_and_succeeds(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        shirt = _kotn_shirt()
        del shirt["name"]
        resp = client.post(url, {"phone": "+16135550100", "shirts": json.dumps([shirt])})
        assert resp.status_code == 302
        entry = PickupEntry.objects.get(business=kotn_business)
        assert entry.intake_answers["Shirts"][0]["name"] == "NO NAME"

    def test_existing_named_order_untouched_by_new_blank_order(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        client.post(url, {"phone": "+16135550100", "shirts": json.dumps([_kotn_shirt("ALI")])})
        client.post(url, {"phone": "+16135550101", "shirts": json.dumps([_kotn_shirt(name="")])})

        named = PickupEntry.objects.get(intake_answers__Shirts__0__name="ALI")
        assert named.intake_answers["Shirts"][0]["name"] == "ALI"
        default_named = PickupEntry.objects.get(intake_answers__Shirts__0__name="NO NAME")
        assert default_named.intake_answers["Shirts"][0]["name"] == "NO NAME"


class TestJoinViewModes:
    def test_queue_only_shows_queue_form(self, client, queue_only_business):
        url = reverse("customer:join", kwargs={"slug": queue_only_business.slug})
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"Join the queue" in resp.content
        assert b"panel-pickup" not in resp.content

    def test_pickup_only_shows_pickup_form(self, client, pickup_only_business):
        url = reverse("customer:join", kwargs={"slug": pickup_only_business.slug})
        resp = client.get(url, follow=True)
        assert resp.status_code == 200
        assert b"Notify me when ready" in resp.content

    def test_pickup_only_redirects_to_branded_pickup_kiosk(self, client, pickup_only_business):
        url = reverse("customer:join", kwargs={"slug": pickup_only_business.slug})
        resp = client.get(url)
        assert resp.status_code == 302
        assert resp.url == reverse("customer:pickup_join", kwargs={"slug": pickup_only_business.slug})

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
        # Phone field is always shown; submit button always present
        assert b"Notify me when ready" in resp.content

    def test_get_shows_order_number_when_enabled(self, client, db):
        """Order number field is shown when field_order_number_enabled=True."""
        biz = Business.objects.create(
            name="Order Biz", slug="order-biz", is_active=True,
            queue_enabled=False, pickup_enabled=True,
            field_order_number_enabled=True,
        )
        url = reverse("customer:pickup_join", kwargs={"slug": biz.slug})
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"order_number" in resp.content

    def test_get_404_when_pickup_disabled(self, client, queue_only_business):
        url = reverse("customer:pickup_join", kwargs={"slug": queue_only_business.slug})
        resp = client.get(url)
        assert resp.status_code == 404

    def test_post_creates_entry_with_phone(self, client, pickup_only_business):
        url = reverse("customer:pickup_join", kwargs={"slug": pickup_only_business.slug})
        resp = client.post(url, {"customer_name": "Alice", "phone": "+16135550100"})
        assert resp.status_code == 302
        entry = PickupEntry.objects.get(business=pickup_only_business, customer_name="Alice")
        assert entry.phone == "+16135550100"

    def test_post_requires_order_number_when_configured(self, client, db):
        """Validation enforces order number when field_order_number_required=True."""
        biz = Business.objects.create(
            name="Order Required", slug="order-req", is_active=True,
            queue_enabled=False, pickup_enabled=True,
            field_order_number_enabled=True,
            field_order_number_required=True,
            field_name_required=False,  # don't block on name
        )
        url = reverse("customer:pickup_join", kwargs={"slug": biz.slug})
        resp = client.post(url, {"order_number": ""})
        assert resp.status_code == 200
        assert b"order number" in resp.content.lower()
        assert PickupEntry.objects.count() == 0

    def test_post_invalid_phone_returns_error(self, client, pickup_only_business):
        url = reverse("customer:pickup_join", kwargs={"slug": pickup_only_business.slug})
        resp = client.post(url, {"customer_name": "Bob", "phone": "not-a-phone"})
        assert resp.status_code == 200
        assert PickupEntry.objects.count() == 0

    def test_post_redirects_to_confirmation(self, client, pickup_only_business):
        url = reverse("customer:pickup_join", kwargs={"slug": pickup_only_business.slug})
        resp = client.post(url, {"customer_name": "Alice", "phone": "+16135550100"})
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
