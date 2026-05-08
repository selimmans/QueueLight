"""Tests for join page field configuration (Phase 22, updated Phase 22b).

Phone is always required — no longer configurable.
Covers:
- Settings save_join_fields action saves name/order_number fields
- Active pickup entries block field config changes
- Join page renders / hides fields based on config
- Form validation respects required / optional settings for name and order_number
- Phone always required — blocks submission when absent
- Confirmation page shows correct message based on phone presence
"""
import pytest
from django.urls import reverse

from businesses.models import Business
from queues.models import PickupEntry

PHONE = "+16135550100"


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
        )
        assert resp.status_code == 302
        pickup_biz.refresh_from_db()
        assert pickup_biz.field_order_number_enabled is True
        assert pickup_biz.field_order_number_required is True

    def test_phone_required_not_configurable(self, admin_client, pickup_biz, settings_url):
        """Phone required/optional is no longer configurable via settings."""
        resp = self._post(
            admin_client, settings_url,
            field_name_enabled="1",
            field_name_required="1",
            field_order_number_enabled="0",
            field_order_number_required="0",
        )
        assert resp.status_code == 302
        # DB field unchanged — it's ignored by server logic
        pickup_biz.refresh_from_db()
        assert pickup_biz.field_name_enabled is True

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
        )
        assert resp.status_code == 200
        assert b"active pickup" in resp.content.lower()
        pickup_biz.refresh_from_db()
        assert pickup_biz.field_name_enabled is True  # unchanged

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
        client.post(settings_url, {
            "action": "save_join_fields",
            "field_name_enabled": "0",
            "field_name_required": "0",
            "field_order_number_enabled": "0",
            "field_order_number_required": "0",
        })
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
        resp = client.get(join_url)
        assert b'name="phone"' in resp.content

    def test_phone_field_has_required_attribute(self, client, pickup_biz, join_url):
        """Phone input always carries the required attribute."""
        resp = client.get(join_url)
        content = resp.content.decode()
        # The phone input must have required
        assert 'name="phone"' in content
        # Confirm no "optional" hint near phone
        assert "Add your number" not in content

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
        assert b'name="order_number"' in resp.content


# ---------------------------------------------------------------------------
# Form validation respects required / optional settings
# ---------------------------------------------------------------------------

class TestJoinPageValidation:
    def test_name_required_blocks_empty_submission(self, client, pickup_biz, join_url):
        # field_name_required=True by default; phone also required
        resp = client.post(join_url, {"customer_name": "", "phone": ""})
        assert resp.status_code == 200
        assert PickupEntry.objects.count() == 0

    def test_name_optional_allows_empty_with_phone(self, client, pickup_biz, join_url):
        pickup_biz.field_name_required = False
        pickup_biz.save()
        resp = client.post(join_url, {"customer_name": "", "phone": PHONE})
        assert resp.status_code == 302
        assert PickupEntry.objects.count() == 1

    def test_order_number_required_blocks_empty(self, client, pickup_biz, join_url):
        pickup_biz.field_order_number_enabled = True
        pickup_biz.field_order_number_required = True
        pickup_biz.field_name_required = False
        pickup_biz.save()
        resp = client.post(join_url, {"order_number": "", "phone": PHONE})
        assert resp.status_code == 200
        assert b"order number" in resp.content.lower()
        assert PickupEntry.objects.count() == 0

    def test_order_number_optional_allows_empty_with_phone(self, client, pickup_biz, join_url):
        pickup_biz.field_order_number_enabled = True
        pickup_biz.field_order_number_required = False
        pickup_biz.field_name_required = False
        pickup_biz.save()
        resp = client.post(join_url, {"order_number": "", "customer_name": "", "phone": PHONE})
        assert resp.status_code == 302
        entry = PickupEntry.objects.get(business=pickup_biz)
        assert entry.order_number.startswith("W")

    def test_phone_always_required_blocks_empty(self, client, pickup_biz, join_url):
        """Phone is required regardless of any field config."""
        resp = client.post(join_url, {"customer_name": "Alice", "phone": ""})
        assert resp.status_code == 200
        assert b"phone" in resp.content.lower()
        assert PickupEntry.objects.count() == 0

    def test_valid_phone_allows_submission(self, client, pickup_biz, join_url):
        resp = client.post(join_url, {"customer_name": "Alice", "phone": PHONE})
        assert resp.status_code == 302
        entry = PickupEntry.objects.get(business=pickup_biz, customer_name="Alice")
        assert entry.phone == PHONE

    def test_explicit_order_number_saved_when_provided(self, client, pickup_biz, join_url):
        pickup_biz.field_order_number_enabled = True
        pickup_biz.field_order_number_required = True
        pickup_biz.field_name_required = False
        pickup_biz.save()
        resp = client.post(join_url, {"order_number": "ORDER-99", "phone": PHONE})
        assert resp.status_code == 302
        entry = PickupEntry.objects.get(business=pickup_biz)
        assert entry.order_number == "ORDER-99"


# ---------------------------------------------------------------------------
# Confirmation page messages
# ---------------------------------------------------------------------------

class TestConfirmationMessages:
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

    def test_confirmation_shows_call_name_when_no_phone(self, client, pickup_biz):
        """PickupService can still create entries without phone (e.g. staff-created)."""
        from queues.pickup_service import PickupService
        entry = PickupService.register(pickup_biz, order_number="XYZ3", customer_name="Charlie")
        url = reverse("customer:pickup_confirmation", kwargs={
            "slug": pickup_biz.slug, "entry_id": entry.pk
        })
        resp = client.get(url)
        assert b"call your name" in resp.content
        assert b"We'll text you" not in resp.content
