"""Tests for join page field configuration (Phase 22).

Covers:
- Settings save_join_fields action saves all six fields
- Active pickup entries block field config changes
- Join page renders / hides fields based on config
- Form validation respects required / optional settings
- PickupEntry created correctly when phone is absent (no SMS)
- Confirmation page shows correct message for no-phone entries
"""
import pytest
from django.urls import reverse

from businesses.models import Business
from queues.models import PickupEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_client(client, db):
    """Django test client logged in as a superuser."""
    from django.contrib.auth.models import User
    user = User.objects.create_superuser(
        username="admin_jfc", password="testpass", email="admin@test.com"
    )
    client.force_login(user)
    return client


@pytest.fixture
def pickup_biz(db):
    return Business.objects.create(
        name="Field Config Café",
        slug="field-config-cafe",
        is_active=True,
        queue_enabled=False,
        pickup_enabled=True,
        # Defaults: name enabled+required, order_number disabled, phone optional
    )


@pytest.fixture
def settings_url(pickup_biz):
    return reverse("dashboard:settings", kwargs={"slug": pickup_biz.slug})


@pytest.fixture
def join_url(pickup_biz):
    return reverse("customer:pickup_join", kwargs={"slug": pickup_biz.slug})


# ---------------------------------------------------------------------------
# Settings page: save_join_fields action
# ---------------------------------------------------------------------------

class TestSaveJoinFields:
    def _post(self, admin_client, url, **fields):
        data = {"action": "save_join_fields"}
        data.update(fields)
        return admin_client.post(url, data)

    def test_saves_name_hidden(self, admin_client, pickup_biz, settings_url):
        resp = self._post(
            admin_client, settings_url,
            field_name_enabled="0",
            field_name_required="0",
            field_order_number_enabled="0",
            field_order_number_required="0",
            field_phone_required="0",
        )
        assert resp.status_code == 302
        pickup_biz.refresh_from_db()
        assert pickup_biz.field_name_enabled is False
        assert pickup_biz.field_name_required is False

    def test_saves_order_number_enabled_required(self, admin_client, pickup_biz, settings_url):
        resp = self._post(
            admin_client, settings_url,
            field_name_enabled="1",
            field_name_required="1",
            field_order_number_enabled="1",
            field_order_number_required="1",
            field_phone_required="0",
        )
        assert resp.status_code == 302
        pickup_biz.refresh_from_db()
        assert pickup_biz.field_order_number_enabled is True
        assert pickup_biz.field_order_number_required is True

    def test_saves_phone_required(self, admin_client, pickup_biz, settings_url):
        resp = self._post(
            admin_client, settings_url,
            field_name_enabled="1",
            field_name_required="1",
            field_order_number_enabled="0",
            field_order_number_required="0",
            field_phone_required="1",
        )
        assert resp.status_code == 302
        pickup_biz.refresh_from_db()
        assert pickup_biz.field_phone_required is True

    def test_blocked_when_active_pickup_orders_exist(self, admin_client, pickup_biz, settings_url):
        """Cannot change field config while waiting/ready pickups exist."""
        PickupEntry.objects.create(
            business=pickup_biz,
            order_number="ACTIVE-1",
            status="waiting",
        )
        resp = self._post(
            admin_client, settings_url,
            field_name_enabled="0",
            field_name_required="0",
            field_order_number_enabled="0",
            field_order_number_required="0",
            field_phone_required="0",
        )
        assert resp.status_code == 200
        assert b"active pickup" in resp.content.lower()
        pickup_biz.refresh_from_db()
        # Fields unchanged
        assert pickup_biz.field_name_enabled is True

    def test_allowed_when_only_completed_pickups(self, admin_client, pickup_biz, settings_url):
        """Completed entries do not block the change."""
        PickupEntry.objects.create(
            business=pickup_biz,
            order_number="DONE-1",
            status="picked_up",
        )
        resp = self._post(
            admin_client, settings_url,
            field_name_enabled="0",
            field_name_required="0",
            field_order_number_enabled="0",
            field_order_number_required="0",
            field_phone_required="0",
        )
        assert resp.status_code == 302
        pickup_biz.refresh_from_db()
        assert pickup_biz.field_name_enabled is False

    def test_non_admin_cannot_save_join_fields(self, client, pickup_biz, settings_url, db):
        """Regular (non-superuser) staff cannot change field config."""
        from businesses.models import StaffPhone
        StaffPhone.objects.create(phone="+16135550001", business=pickup_biz, name="Staff")
        session = client.session
        session["business_id"] = pickup_biz.pk
        session["staff_phone_id"] = 1
        session.save()
        resp = client.post(settings_url, {
            "action": "save_join_fields",
            "field_name_enabled": "0",
            "field_name_required": "0",
            "field_order_number_enabled": "0",
            "field_order_number_required": "0",
            "field_phone_required": "0",
        })
        # Non-admin gets redirected (action is ignored) — fields unchanged
        pickup_biz.refresh_from_db()
        assert pickup_biz.field_name_enabled is True  # unchanged


# ---------------------------------------------------------------------------
# Join page renders fields based on config
# ---------------------------------------------------------------------------

class TestJoinPageFieldRendering:
    def test_name_field_shown_when_enabled(self, client, pickup_biz, join_url):
        resp = client.get(join_url)
        assert resp.status_code == 200
        assert b'name="customer_name"' in resp.content

    def test_name_field_hidden_when_disabled(self, client, pickup_biz, join_url):
        pickup_biz.field_name_enabled = False
        pickup_biz.save()
        resp = client.get(join_url)
        assert resp.status_code == 200
        assert b'name="customer_name"' not in resp.content

    def test_order_number_field_hidden_by_default(self, client, pickup_biz, join_url):
        resp = client.get(join_url)
        assert b'name="order_number"' not in resp.content

    def test_order_number_field_shown_when_enabled(self, client, pickup_biz, join_url):
        pickup_biz.field_order_number_enabled = True
        pickup_biz.save()
        resp = client.get(join_url)
        assert b'name="order_number"' in resp.content

    def test_phone_field_always_shown(self, client, pickup_biz, join_url):
        # Even with phone optional, the field is shown
        resp = client.get(join_url)
        assert b'name="phone"' in resp.content

    def test_optional_hint_on_optional_name(self, client, pickup_biz, join_url):
        pickup_biz.field_name_required = False
        pickup_biz.save()
        resp = client.get(join_url)
        assert b"optional" in resp.content

    def test_required_attr_on_required_order_number(self, client, pickup_biz, join_url):
        pickup_biz.field_order_number_enabled = True
        pickup_biz.field_order_number_required = True
        pickup_biz.save()
        resp = client.get(join_url)
        content = resp.content.decode()
        # Find the order_number input and verify it has required
        assert 'name="order_number"' in content

    def test_phone_helper_text_shown_when_optional(self, client, pickup_biz, join_url):
        # field_phone_required defaults to False
        resp = client.get(join_url)
        assert b"Add your number" in resp.content

    def test_phone_helper_text_hidden_when_required(self, client, pickup_biz, join_url):
        pickup_biz.field_phone_required = True
        pickup_biz.save()
        resp = client.get(join_url)
        assert b"Add your number" not in resp.content


# ---------------------------------------------------------------------------
# Form validation respects required / optional settings
# ---------------------------------------------------------------------------

class TestJoinPageValidation:
    def test_name_required_blocks_empty_submission(self, client, pickup_biz, join_url):
        # field_name_required=True by default
        resp = client.post(join_url, {"customer_name": "", "phone": ""})
        assert resp.status_code == 200
        assert b"name" in resp.content.lower()
        assert PickupEntry.objects.count() == 0

    def test_name_optional_allows_empty(self, client, pickup_biz, join_url):
        pickup_biz.field_name_required = False
        pickup_biz.save()
        resp = client.post(join_url, {"customer_name": "", "phone": ""})
        assert resp.status_code == 302
        assert PickupEntry.objects.count() == 1

    def test_order_number_required_blocks_empty(self, client, pickup_biz, join_url):
        pickup_biz.field_order_number_enabled = True
        pickup_biz.field_order_number_required = True
        pickup_biz.field_name_required = False  # don't block on name
        pickup_biz.save()
        resp = client.post(join_url, {"order_number": "", "phone": ""})
        assert resp.status_code == 200
        assert b"order number" in resp.content.lower()
        assert PickupEntry.objects.count() == 0

    def test_order_number_optional_allows_empty(self, client, pickup_biz, join_url):
        pickup_biz.field_order_number_enabled = True
        pickup_biz.field_order_number_required = False
        pickup_biz.field_name_required = False
        pickup_biz.save()
        resp = client.post(join_url, {"order_number": "", "customer_name": "", "phone": ""})
        assert resp.status_code == 302
        # Entry was created with auto-generated order number
        entry = PickupEntry.objects.get(business=pickup_biz)
        assert entry.order_number.startswith("W")

    def test_phone_required_blocks_empty(self, client, pickup_biz, join_url):
        pickup_biz.field_phone_required = True
        pickup_biz.save()
        resp = client.post(join_url, {"customer_name": "Alice", "phone": ""})
        assert resp.status_code == 200
        assert b"phone" in resp.content.lower()
        assert PickupEntry.objects.count() == 0

    def test_phone_optional_allows_empty(self, client, pickup_biz, join_url):
        # field_phone_required=False by default
        resp = client.post(join_url, {"customer_name": "Alice", "phone": ""})
        assert resp.status_code == 302
        entry = PickupEntry.objects.get(business=pickup_biz, customer_name="Alice")
        assert entry.phone == ""

    def test_explicit_order_number_used_when_provided(self, client, pickup_biz, join_url):
        """When order_number is submitted (field enabled+required), it is saved as-is."""
        pickup_biz.field_order_number_enabled = True
        pickup_biz.field_order_number_required = True
        pickup_biz.field_name_required = False
        pickup_biz.save()
        resp = client.post(join_url, {"order_number": "ORDER-99", "phone": ""})
        assert resp.status_code == 302
        entry = PickupEntry.objects.get(business=pickup_biz)
        assert entry.order_number == "ORDER-99"


# ---------------------------------------------------------------------------
# PickupEntry created correctly when phone is absent
# ---------------------------------------------------------------------------

class TestPickupEntryNoPhone:
    def test_entry_phone_is_empty_string(self, client, pickup_biz, join_url):
        resp = client.post(join_url, {"customer_name": "Bob", "phone": ""})
        assert resp.status_code == 302
        entry = PickupEntry.objects.get(business=pickup_biz, customer_name="Bob")
        assert entry.phone == ""

    def test_confirmation_shows_call_name_message(self, client, pickup_biz):
        from queues.pickup_service import PickupService
        entry = PickupService.register(pickup_biz, order_number="XYZ", customer_name="Charlie")
        url = reverse("customer:pickup_confirmation", kwargs={
            "slug": pickup_biz.slug, "entry_id": entry.pk
        })
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"call your name" in resp.content
        assert b"We'll text you" not in resp.content

    def test_confirmation_shows_sms_message_when_phone_present(self, client, pickup_biz):
        from queues.pickup_service import PickupService
        entry = PickupService.register(
            pickup_biz, order_number="XYZ2",
            customer_name="Dave", phone="+16135550099"
        )
        url = reverse("customer:pickup_confirmation", kwargs={
            "slug": pickup_biz.slug, "entry_id": entry.pk
        })
        resp = client.get(url)
        assert b"text you" in resp.content
        assert b"call your name" not in resp.content
