import json

import pytest
from django.urls import reverse

from businesses.models import Business
from customer.views import (
    KOTN_ORDER_MAX,
    KOTN_PATCH_MAX_PER_SHIRT,
    KOTN_PATCHES,
    KOTN_POPUP_SLUG,
)
from queues.models import PickupEntry


@pytest.fixture
def kotn_business(db):
    return Business.objects.create(
        name="Kotn Cup 26", slug=KOTN_POPUP_SLUG, is_active=True,
        queue_enabled=False, pickup_enabled=True,
    )


def _shirt(**overrides):
    data = {
        "patches": [KOTN_PATCHES[0]["key"]],
        "sleeve": "short-sleeve",
        "name": "Sam",
    }
    data.update(overrides)
    return data


def _post(shirts, phone="+16135550100"):
    return {"shirts": json.dumps(shirts), "phone": phone}


class TestKotnJoinPage:
    def test_get_uses_branded_template(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"Pick Your Patch" in resp.content
        content = resp.content.decode()
        for p in KOTN_PATCHES:
            assert p["name"] in content


class TestKotnShirtValidation:
    def test_no_shirts_rejected(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        resp = client.post(url, _post([]))
        assert resp.status_code == 400
        assert b"at least one shirt" in resp.content
        assert not PickupEntry.objects.filter(business=kotn_business).exists()

    def test_invalid_patch_key_rejected(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        resp = client.post(url, _post([_shirt(patches=["not-a-real-patch"])]))
        assert resp.status_code == 400
        assert b"valid patches" in resp.content

    def test_more_than_max_patches_rejected(self, client, kotn_business):
        too_many = [p["key"] for p in KOTN_PATCHES][: KOTN_PATCH_MAX_PER_SHIRT + 1]
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        resp = client.post(url, _post([_shirt(patches=too_many)]))
        assert resp.status_code == 400
        assert b"valid patches" in resp.content

    def test_two_patches_allowed(self, client, kotn_business):
        two = [KOTN_PATCHES[0]["key"], KOTN_PATCHES[1]["key"]]
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        resp = client.post(url, _post([_shirt(patches=two)]))
        assert resp.status_code == 302
        entry = PickupEntry.objects.get(business=kotn_business)
        assert len(entry.intake_answers["Shirts"][0]["patches"]) == 2

    def test_invalid_sleeve_rejected(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        resp = client.post(url, _post([_shirt(sleeve="medium")]))
        assert resp.status_code == 400
        assert b"sleeve length" in resp.content

    def test_missing_name_rejected(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        resp = client.post(url, _post([_shirt(name="")]))
        assert resp.status_code == 400
        assert b"needs a name" in resp.content

    def test_name_over_max_length_rejected(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        resp = client.post(url, _post([_shirt(name="TooLongName")]))
        assert resp.status_code == 400
        assert b"8 characters or fewer" in resp.content

    def test_name_is_uppercased(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        client.post(url, _post([_shirt(name="sam")]))
        entry = PickupEntry.objects.get(business=kotn_business)
        assert entry.intake_answers["Shirts"][0]["name"] == "SAM"

    def test_missing_phone_rejected(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        resp = client.post(url, _post([_shirt()], phone=""))
        assert resp.status_code == 400
        assert b"phone number" in resp.content


class TestKotnSingleShirtOrder:
    def test_valid_submission_creates_entry(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        resp = client.post(url, _post([_shirt(name="sam")]))
        assert resp.status_code == 302
        entry = PickupEntry.objects.get(business=kotn_business)
        assert entry.order_number == "001"
        assert entry.customer_name == "SAM"
        shirts = entry.intake_answers["Shirts"]
        assert len(shirts) == 1
        assert shirts[0]["tag"] == "001"
        assert shirts[0]["patches"][0]["name"] == KOTN_PATCHES[0]["name"]
        assert shirts[0]["sleeve"] == "Short Sleeve"


class TestKotnMultiShirtOrder:
    def test_two_shirts_get_two_sequential_tags(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        shirts = [_shirt(name="sam"), _shirt(name="ziad", patches=[KOTN_PATCHES[1]["key"]])]
        resp = client.post(url, _post(shirts))
        assert resp.status_code == 302
        entry = PickupEntry.objects.get(business=kotn_business)
        assert entry.order_number == "001–002"
        assert entry.customer_name == "SAM / ZIAD"
        stored = entry.intake_answers["Shirts"]
        assert [s["tag"] for s in stored] == ["001", "002"]

    def test_tags_are_global_not_per_order(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        client.post(url, _post([_shirt(name="one")]))
        client.post(url, _post([_shirt(name="two"), _shirt(name="three")]))
        client.post(url, _post([_shirt(name="four")]))
        entries = PickupEntry.objects.filter(business=kotn_business).order_by("id")
        assert [e.order_number for e in entries] == ["001", "002–003", "004"]

    def test_capacity_reached_blocks_whole_order(self, client, kotn_business, db):
        # Fill capacity to 299 used tags via one big legacy-style entry list,
        # leaving room for only 1 more tag.
        PickupEntry.objects.create(
            business=kotn_business, order_number="001–299", customer_name="Bulk",
            phone="+16135550100",
            intake_answers={"Shirts": [
                {"tag": f"{i:03d}", "patches": [], "sleeve": "Short Sleeve", "name": "X"}
                for i in range(1, KOTN_ORDER_MAX)
            ]},
        )
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        # 2 shirts requested but only 1 tag (300) remains -> whole order rejected
        resp = client.post(url, _post([_shirt(name="a"), _shirt(name="b")]))
        assert resp.status_code == 400
        assert b"capacity" in resp.content.lower()
        assert PickupEntry.objects.filter(business=kotn_business).count() == 1

        # 1 shirt requested -> exactly fits
        resp = client.post(url, _post([_shirt(name="a")]))
        assert resp.status_code == 302
        assert PickupEntry.objects.filter(business=kotn_business).count() == 2

    def test_legacy_single_shirt_entry_counted_in_tag_pool(self, client, kotn_business, db):
        # Old-format entry (pre-multi-shirt): order_number IS the tag, no Shirts list.
        PickupEntry.objects.create(
            business=kotn_business, order_number="001", customer_name="LEGACY",
            phone="+16135550100", intake_answers={"Patch": "Toronto", "Size": "Short Sleeve"},
        )
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        client.post(url, _post([_shirt(name="new")]))
        newest = PickupEntry.objects.filter(business=kotn_business).exclude(customer_name="LEGACY").get()
        assert newest.order_number == "002"

    def test_other_business_tags_dont_collide_with_kotn(self, client, kotn_business, db):
        other = Business.objects.create(
            name="Other", slug="other-pickup", is_active=True,
            queue_enabled=False, pickup_enabled=True,
        )
        PickupEntry.objects.create(
            business=other, order_number="001", customer_name="X", phone="+16135550100",
        )
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        client.post(url, _post([_shirt()]))
        entry = PickupEntry.objects.get(business=kotn_business)
        assert entry.order_number == "001"
