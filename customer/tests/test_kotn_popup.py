import pytest
from django.urls import reverse

from businesses.models import Business
from customer.views import KOTN_ORDER_MAX, KOTN_PATCHES, KOTN_POPUP_SLUG
from queues.models import PickupEntry


@pytest.fixture
def kotn_business(db):
    return Business.objects.create(
        name="Kotn Cup 26", slug=KOTN_POPUP_SLUG, is_active=True,
        queue_enabled=False, pickup_enabled=True,
    )


def _valid_post(**overrides):
    data = {
        "customer_name": "Sam",
        "phone": "+16135550100",
        "patch": KOTN_PATCHES[0]["key"],
        "size": "short-sleeve",
    }
    data.update(overrides)
    return data


class TestKotnJoinValidation:
    def test_get_uses_branded_template(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"Pick Your Patch" in resp.content
        content = resp.content.decode()
        for p in KOTN_PATCHES:
            assert p["name"] in content

    def test_name_over_max_length_rejected(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        resp = client.post(url, _valid_post(customer_name="TooLongName"))
        assert resp.status_code == 200
        assert b"8 characters or fewer" in resp.content
        assert not PickupEntry.objects.filter(business=kotn_business).exists()

    def test_name_is_uppercased(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        client.post(url, _valid_post(customer_name="sam"))
        entry = PickupEntry.objects.get(business=kotn_business)
        assert entry.customer_name == "SAM"

    def test_invalid_patch_key_rejected(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        resp = client.post(url, _valid_post(patch="not-a-real-patch"))
        assert resp.status_code == 200
        assert b"Please choose a patch" in resp.content
        assert not PickupEntry.objects.filter(business=kotn_business).exists()

    def test_missing_size_rejected(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        resp = client.post(url, _valid_post(size=""))
        assert resp.status_code == 200
        assert b"Please choose a size" in resp.content

    def test_valid_submission_creates_entry(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        resp = client.post(url, _valid_post(patch="toronto"))
        assert resp.status_code == 302
        entry = PickupEntry.objects.get(business=kotn_business)
        assert entry.intake_answers["Patch"] == "Toronto"
        assert entry.intake_answers["Size"] == "Short Sleeve"


class TestKotnOrderNumberAssignment:
    def test_first_entry_gets_order_number_001(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        client.post(url, _valid_post())
        entry = PickupEntry.objects.get(business=kotn_business)
        assert entry.order_number == "001"

    def test_order_numbers_are_sequential_and_zero_padded(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        for _ in range(3):
            client.post(url, _valid_post())
        numbers = sorted(
            PickupEntry.objects.filter(business=kotn_business).values_list("order_number", flat=True)
        )
        assert numbers == ["001", "002", "003"]

    def test_customer_cannot_set_order_number(self, client, kotn_business):
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        client.post(url, _valid_post(order_number="999"))
        entry = PickupEntry.objects.get(business=kotn_business)
        assert entry.order_number == "001"

    def test_capacity_reached_blocks_new_entries(self, client, kotn_business, db):
        for i in range(1, KOTN_ORDER_MAX + 1):
            PickupEntry.objects.create(
                business=kotn_business, order_number=f"{i:03d}", customer_name=f"C{i}",
                phone="+16135550100",
            )
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        resp = client.post(url, _valid_post())
        assert resp.status_code == 200
        assert b"capacity" in resp.content.lower()
        assert PickupEntry.objects.filter(business=kotn_business).count() == KOTN_ORDER_MAX

    def test_other_business_order_numbers_dont_collide_with_kotn(self, client, kotn_business, db):
        other = Business.objects.create(
            name="Other", slug="other-pickup", is_active=True,
            queue_enabled=False, pickup_enabled=True,
        )
        PickupEntry.objects.create(
            business=other, order_number="001", customer_name="X", phone="+16135550100",
        )
        url = reverse("customer:pickup_join", kwargs={"slug": kotn_business.slug})
        client.post(url, _valid_post())
        entry = PickupEntry.objects.get(business=kotn_business)
        assert entry.order_number == "001"
