from unittest.mock import patch

import pytest
from django.urls import reverse

from businesses.models import Business, StaffPhone
from queues.models import PickupEntry
from queues.pickup_service import PickupService

SESSION_BUSINESS = "business_id"
SESSION_STAFF = "staff_phone_id"


@pytest.fixture
def pickup_business(db):
    return Business.objects.create(
        name="Pickup Café",
        slug="pickup-cafe",
        is_active=True,
        queue_enabled=False,
        pickup_enabled=True,
        twilio_from_number="+15005550006",
    )


@pytest.fixture
def pickup_staff(db, pickup_business):
    return StaffPhone.objects.create(
        phone="+16135550010", business=pickup_business, name="Staff"
    )


def _login(client, business, staff):
    session = client.session
    session[SESSION_BUSINESS] = business.pk
    session[SESSION_STAFF] = staff.pk
    session.save()


class TestPickupDashboardSection:
    def test_dashboard_shows_pickup_section(self, client, pickup_business, pickup_staff):
        _login(client, pickup_business, pickup_staff)
        PickupService.register(pickup_business, order_number="42")
        url = reverse("dashboard:dashboard", kwargs={"slug": pickup_business.slug})
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"42" in resp.content
        assert b"pickup-list" in resp.content

    def test_dashboard_shows_avg_wait(self, client, pickup_business, pickup_staff):
        _login(client, pickup_business, pickup_staff)
        PickupService.register(pickup_business, order_number="42")
        url = reverse("dashboard:dashboard", kwargs={"slug": pickup_business.slug})
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp.context["avg_wait_minutes"] == 0
        assert b"avg-wait-stat" in resp.content

    def test_dashboard_avg_wait_none_when_no_active_orders(self, client, pickup_business, pickup_staff):
        _login(client, pickup_business, pickup_staff)
        url = reverse("dashboard:dashboard", kwargs={"slug": pickup_business.slug})
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp.context["avg_wait_minutes"] is None

    def test_dashboard_no_pickup_section_when_disabled(self, client, db):
        biz = Business.objects.create(
            name="No Pickup", slug="no-pickup", is_active=True,
            queue_enabled=True, pickup_enabled=False,
        )
        sp = StaffPhone.objects.create(phone="+16135550020", business=biz, name="Staff")
        _login(client, biz, sp)
        url = reverse("dashboard:dashboard", kwargs={"slug": biz.slug})
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"pickup-list" not in resp.content


class TestPickupReadyView:
    def test_mark_ready_changes_status(self, client, pickup_business, pickup_staff):
        _login(client, pickup_business, pickup_staff)
        entry = PickupService.register(pickup_business, order_number="10")
        url = reverse("dashboard:pickup_ready", kwargs={
            "slug": pickup_business.slug, "entry_id": entry.pk
        })
        resp = client.post(url)
        assert resp.status_code == 302
        entry.refresh_from_db()
        assert entry.status == PickupEntry.Status.READY

    def test_requires_session(self, client, pickup_business):
        entry = PickupService.register(pickup_business, order_number="10")
        url = reverse("dashboard:pickup_ready", kwargs={
            "slug": pickup_business.slug, "entry_id": entry.pk
        })
        resp = client.post(url)
        assert resp.status_code == 302
        assert "login" in resp["Location"]


class TestPickupResetTagsView:
    def test_reset_sets_business_timestamp(self, client, pickup_business, pickup_staff):
        _login(client, pickup_business, pickup_staff)
        assert pickup_business.pickup_tag_reset_at is None
        url = reverse("dashboard:pickup_reset_tags", kwargs={"slug": pickup_business.slug})
        resp = client.post(url)
        assert resp.status_code == 302
        pickup_business.refresh_from_db()
        assert pickup_business.pickup_tag_reset_at is not None

    def test_requires_session(self, client, pickup_business):
        url = reverse("dashboard:pickup_reset_tags", kwargs={"slug": pickup_business.slug})
        resp = client.post(url)
        assert resp.status_code == 302
        assert "login" in resp["Location"]
        assert pickup_business.pickup_tag_reset_at is None


class TestPickupPickedUpView:
    def test_mark_picked_up(self, client, pickup_business, pickup_staff):
        _login(client, pickup_business, pickup_staff)
        entry = PickupService.register(pickup_business, order_number="20")
        PickupService.mark_ready(entry)
        url = reverse("dashboard:pickup_picked_up", kwargs={
            "slug": pickup_business.slug, "entry_id": entry.pk
        })
        resp = client.post(url)
        assert resp.status_code == 302
        entry.refresh_from_db()
        assert entry.status == PickupEntry.Status.PICKED_UP


class TestPickupResendSmsView:
    @patch("queues.pickup_service.TwilioSMSBackend.send")
    def test_resend_sends_sms(self, mock_send, client, pickup_business, pickup_staff):
        mock_send.return_value = (True, "")
        _login(client, pickup_business, pickup_staff)
        entry = PickupService.register(pickup_business, order_number="30", phone="+16135550030")
        PickupService.mark_ready(entry)
        mock_send.reset_mock()

        url = reverse("dashboard:pickup_resend_sms", kwargs={
            "slug": pickup_business.slug, "entry_id": entry.pk
        })
        resp = client.post(url)

        assert resp.status_code == 302
        mock_send.assert_called_once()

    def test_requires_session(self, client, pickup_business):
        entry = PickupService.register(pickup_business, order_number="30", phone="+16135550030")
        url = reverse("dashboard:pickup_resend_sms", kwargs={
            "slug": pickup_business.slug, "entry_id": entry.pk
        })
        resp = client.post(url)
        assert resp.status_code == 302
        assert "login" in resp["Location"]

    def test_dashboard_shows_resend_button_for_ready_order_with_phone(self, client, pickup_business, pickup_staff):
        _login(client, pickup_business, pickup_staff)
        entry = PickupService.register(pickup_business, order_number="31", phone="+16135550031")
        PickupService.mark_ready(entry)
        url = reverse("dashboard:dashboard", kwargs={"slug": pickup_business.slug})
        resp = client.get(url)
        resend_url = reverse("dashboard:pickup_resend_sms", kwargs={
            "slug": pickup_business.slug, "entry_id": entry.pk
        })
        assert resend_url.encode() in resp.content

    def test_dashboard_hides_resend_button_when_no_phone(self, client, pickup_business, pickup_staff):
        _login(client, pickup_business, pickup_staff)
        entry = PickupService.register(pickup_business, order_number="32")
        PickupService.mark_ready(entry)
        url = reverse("dashboard:dashboard", kwargs={"slug": pickup_business.slug})
        resp = client.get(url)
        resend_url = reverse("dashboard:pickup_resend_sms", kwargs={
            "slug": pickup_business.slug, "entry_id": entry.pk
        })
        assert resend_url.encode() not in resp.content


class TestPickupStatusAPI:
    def test_returns_active_entries(self, client, pickup_business, pickup_staff):
        _login(client, pickup_business, pickup_staff)
        PickupService.register(pickup_business, order_number="5")
        PickupService.register(pickup_business, order_number="6")
        resp = client.get(f"/api/pickup/{pickup_business.slug}/status/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["active_orders"]) == 2
        assert data["total_active"] == 2

    def test_excludes_picked_up_entries(self, client, pickup_business, pickup_staff):
        _login(client, pickup_business, pickup_staff)
        entry = PickupService.register(pickup_business, order_number="5")
        PickupService.mark_ready(entry)
        PickupService.mark_picked_up(entry)
        resp = client.get(f"/api/pickup/{pickup_business.slug}/status/")
        data = resp.json()
        assert len(data["active_orders"]) == 0
        assert data["total_active"] == 0

    def test_requires_auth(self, client, pickup_business):
        resp = client.get(f"/api/pickup/{pickup_business.slug}/status/")
        assert resp.status_code == 401

    def test_response_includes_minutes_waiting(self, client, pickup_business, pickup_staff):
        _login(client, pickup_business, pickup_staff)
        PickupService.register(pickup_business, order_number="77")
        resp = client.get(f"/api/pickup/{pickup_business.slug}/status/")
        data = resp.json()
        assert "minutes_waiting" in data["active_orders"][0]
        assert isinstance(data["active_orders"][0]["minutes_waiting"], int)

    def test_response_shape(self, client, pickup_business, pickup_staff):
        _login(client, pickup_business, pickup_staff)
        PickupService.register(pickup_business, order_number="99", customer_name="Bob")
        resp = client.get(f"/api/pickup/{pickup_business.slug}/status/")
        data = resp.json()
        order = data["active_orders"][0]
        assert order["order_number"] == "99"
        assert order["customer_name"] == "Bob"
        assert order["status"] == "waiting"
        assert "registered_at" in order


class TestDashboardMode:
    """Verify correct panel/tab HTML rendered for each feature combination."""

    def _make_biz_and_staff(self, db, slug, queue_enabled, pickup_enabled):
        biz = Business.objects.create(
            name="Test Biz", slug=slug, is_active=True,
            queue_enabled=queue_enabled, pickup_enabled=pickup_enabled,
        )
        sp = StaffPhone.objects.create(phone="+16135559900", business=biz, name="Staff")
        return biz, sp

    def test_queue_only_no_tab_bar(self, client, db):
        biz, sp = self._make_biz_and_staff(db, "q-only", True, False)
        _login(client, biz, sp)
        resp = client.get(reverse("dashboard:dashboard", kwargs={"slug": biz.slug}))
        assert resp.status_code == 200
        assert b"tabBtnQueue" not in resp.content
        assert b"tabBtnPickup" not in resp.content
        assert b"panel-queue" in resp.content

    def test_pickup_only_no_tab_bar(self, client, db):
        biz, sp = self._make_biz_and_staff(db, "p-only", False, True)
        _login(client, biz, sp)
        resp = client.get(reverse("dashboard:dashboard", kwargs={"slug": biz.slug}))
        assert resp.status_code == 200
        assert b"tabBtnQueue" not in resp.content
        assert b"tabBtnPickup" not in resp.content
        assert b"panel-pickup" in resp.content
        assert b"panel-queue" not in resp.content

    def test_both_shows_tab_bar(self, client, db):
        biz, sp = self._make_biz_and_staff(db, "b-both", True, True)
        _login(client, biz, sp)
        resp = client.get(reverse("dashboard:dashboard", kwargs={"slug": biz.slug}))
        assert resp.status_code == 200
        assert b"tab-bar" in resp.content
        assert b"tabBtnQueue" in resp.content
        assert b"tabBtnPickup" in resp.content
        assert b"panel-queue" in resp.content
        assert b"panel-pickup" in resp.content

    def test_inactive_shows_notice(self, client, db):
        biz, sp = self._make_biz_and_staff(db, "inactive-d", False, False)
        _login(client, biz, sp)
        resp = client.get(reverse("dashboard:dashboard", kwargs={"slug": biz.slug}))
        assert resp.status_code == 200
        assert b"tabBtnQueue" not in resp.content
        assert b"tabBtnPickup" not in resp.content
        assert b"inactive-notice" in resp.content

    def test_dashboard_mode_context_both(self, client, db):
        biz, sp = self._make_biz_and_staff(db, "ctx-both", True, True)
        _login(client, biz, sp)
        resp = client.get(reverse("dashboard:dashboard", kwargs={"slug": biz.slug}))
        assert resp.context["dashboard_mode"] == "both"

    def test_dashboard_mode_context_queue_only(self, client, db):
        biz, sp = self._make_biz_and_staff(db, "ctx-q", True, False)
        _login(client, biz, sp)
        resp = client.get(reverse("dashboard:dashboard", kwargs={"slug": biz.slug}))
        assert resp.context["dashboard_mode"] == "queue_only"

    def test_dashboard_mode_context_pickup_only(self, client, db):
        biz, sp = self._make_biz_and_staff(db, "ctx-p", False, True)
        _login(client, biz, sp)
        resp = client.get(reverse("dashboard:dashboard", kwargs={"slug": biz.slug}))
        assert resp.context["dashboard_mode"] == "pickup_only"


class TestSettingsFeatureToggles:
    def test_toggle_pickup_on(self, client, db):
        biz = Business.objects.create(
            name="Toggle Test", slug="toggle-test", is_active=True,
            queue_enabled=True, pickup_enabled=False,
        )
        sp = StaffPhone.objects.create(phone="+16135550030", business=biz, name="Staff")
        _login(client, biz, sp)
        url = reverse("dashboard:settings", kwargs={"slug": biz.slug})
        client.post(url, {"action": "toggle_pickup", "pickup_enabled": "1"})
        biz.refresh_from_db()
        assert biz.pickup_enabled is True

    def test_toggle_queue_off_blocked_when_queue_not_empty(self, client, db):
        from queues.models import QueueEntry
        biz = Business.objects.create(
            name="Queue Block", slug="queue-block", is_active=True,
            queue_enabled=True, pickup_enabled=False,
        )
        sp = StaffPhone.objects.create(phone="+16135550040", business=biz, name="Staff")
        QueueEntry.objects.create(
            business=biz, name="A", phone="+16135550099",
            status=QueueEntry.Status.WAITING, position=1,
        )
        _login(client, biz, sp)
        url = reverse("dashboard:settings", kwargs={"slug": biz.slug})
        resp = client.post(url, {"action": "toggle_queue", "queue_enabled": "0"})
        assert resp.status_code == 200
        biz.refresh_from_db()
        assert biz.queue_enabled is True

    def test_toggle_queue_off_allowed_when_empty(self, client, db):
        biz = Business.objects.create(
            name="Queue Empty", slug="queue-empty", is_active=True,
            queue_enabled=True, pickup_enabled=False,
        )
        sp = StaffPhone.objects.create(phone="+16135550050", business=biz, name="Staff")
        _login(client, biz, sp)
        url = reverse("dashboard:settings", kwargs={"slug": biz.slug})
        client.post(url, {"action": "toggle_queue", "queue_enabled": "0"})
        biz.refresh_from_db()
        assert biz.queue_enabled is False


class TestSettingsPickupSms:
    def test_save_pickup_sms_updates_message(self, client, pickup_business, pickup_staff):
        _login(client, pickup_business, pickup_staff)
        url = reverse("dashboard:settings", kwargs={"slug": pickup_business.slug})
        message = "Hey, thank you for being a part of Kotn Cup. Your jersey is ready!"
        client.post(url, {"action": "save_pickup_sms", "pickup_notification_message": message})
        pickup_business.refresh_from_db()
        assert pickup_business.pickup_notification_message == message

    def test_save_pickup_sms_does_not_touch_intake_fields(self, client, pickup_business, pickup_staff):
        pickup_business.pickup_intake_fields = ["Any allergies?"]
        pickup_business.save(update_fields=["pickup_intake_fields"])
        _login(client, pickup_business, pickup_staff)
        url = reverse("dashboard:settings", kwargs={"slug": pickup_business.slug})
        client.post(url, {"action": "save_pickup_sms", "pickup_notification_message": "New message"})
        pickup_business.refresh_from_db()
        assert pickup_business.pickup_intake_fields == ["Any allergies?"]


class TestSettingsPickupIntake:
    def test_save_pickup_intake_updates_questions(self, client, pickup_business, pickup_staff):
        _login(client, pickup_business, pickup_staff)
        url = reverse("dashboard:settings", kwargs={"slug": pickup_business.slug})
        client.post(url, {"action": "save_pickup_intake", "pickup_intake_questions": ["Any allergies?"]})
        pickup_business.refresh_from_db()
        assert pickup_business.pickup_intake_fields == ["Any allergies?"]

    def test_save_pickup_intake_does_not_touch_sms_message(self, client, pickup_business, pickup_staff):
        pickup_business.pickup_notification_message = "Custom ready message"
        pickup_business.save(update_fields=["pickup_notification_message"])
        _login(client, pickup_business, pickup_staff)
        url = reverse("dashboard:settings", kwargs={"slug": pickup_business.slug})
        client.post(url, {"action": "save_pickup_intake", "pickup_intake_questions": []})
        pickup_business.refresh_from_db()
        assert pickup_business.pickup_notification_message == "Custom ready message"


# ---------------------------------------------------------------------------
# Unregistered POS orders in /api/pickup/<slug>/status/
# ---------------------------------------------------------------------------

_FAKE_POS_ORDER = {
    "id": "POS-001",
    "customer_name": "Ahmed",
    "items": ["Pistachio Latte", "Muffin"],
    "created_at": "2026-05-07T14:23:00+00:00",
}


class TestPickupStatusAPIUnregistered:
    """Section 2: POS orders that have no matching PickupEntry."""

    def _pos_biz(self, db, slug="pos-biz"):
        """Business with a POS integration configured."""
        biz = Business.objects.create(
            name="POS Café",
            slug=slug,
            is_active=True,
            queue_enabled=False,
            pickup_enabled=True,
            pos_type="clover",
            pos_api_token="tok",
            pos_merchant_id="mid",
        )
        sp = StaffPhone.objects.create(phone="+16135550060", business=biz, name="Staff")
        return biz, sp

    def test_no_pos_returns_empty_unregistered(self, client, pickup_business, pickup_staff):
        """When pos_type=none, unregistered_orders is always empty."""
        _login(client, pickup_business, pickup_staff)
        resp = client.get(f"/api/pickup/{pickup_business.slug}/status/")
        data = resp.json()
        assert data["unregistered_orders"] == []
        assert data["total_unregistered"] == 0

    def test_unregistered_order_returned(self, client, db):
        """A POS order with no matching PickupEntry appears in unregistered_orders."""
        from unittest.mock import patch
        biz, sp = self._pos_biz(db)
        _login(client, biz, sp)
        with patch(
            "notifications.pos_integration.POSIntegration.get_recent_orders",
            return_value=[_FAKE_POS_ORDER],
        ):
            resp = client.get(f"/api/pickup/{biz.slug}/status/")
        data = resp.json()
        assert data["total_unregistered"] == 1
        assert data["unregistered_orders"][0]["pos_order_id"] == "POS-001"
        assert data["unregistered_orders"][0]["customer_name"] == "Ahmed"
        assert data["unregistered_orders"][0]["items"] == ["Pistachio Latte", "Muffin"]

    def test_registered_entry_excluded_from_unregistered(self, client, db):
        """A POS order whose id matches a PickupEntry.pos_order_id is excluded."""
        from unittest.mock import patch
        biz, sp = self._pos_biz(db, slug="pos-biz-2")
        _login(client, biz, sp)
        # Register the customer — link their entry to the POS order
        entry = PickupService.register(biz, order_number="POS-001")
        entry.pos_order_id = "POS-001"
        entry.save(update_fields=["pos_order_id"])
        with patch(
            "notifications.pos_integration.POSIntegration.get_recent_orders",
            return_value=[_FAKE_POS_ORDER],
        ):
            resp = client.get(f"/api/pickup/{biz.slug}/status/")
        data = resp.json()
        assert data["total_unregistered"] == 0
        assert data["unregistered_orders"] == []

    def test_unregistered_order_shape(self, client, db):
        """unregistered_orders items have all required keys."""
        from unittest.mock import patch
        biz, sp = self._pos_biz(db, slug="pos-biz-3")
        _login(client, biz, sp)
        with patch(
            "notifications.pos_integration.POSIntegration.get_recent_orders",
            return_value=[_FAKE_POS_ORDER],
        ):
            resp = client.get(f"/api/pickup/{biz.slug}/status/")
        item = resp.json()["unregistered_orders"][0]
        assert "pos_order_id" in item
        assert "customer_name" in item
        assert "items" in item
        assert "ordered_at" in item
        assert "minutes_ago" in item

    def test_pos_failure_returns_empty_unregistered(self, client, db):
        """If the POS API call raises, the endpoint still returns 200 with empty list."""
        from unittest.mock import patch
        biz, sp = self._pos_biz(db, slug="pos-biz-4")
        _login(client, biz, sp)
        with patch(
            "notifications.pos_integration.POSIntegration.get_recent_orders",
            side_effect=RuntimeError("Network error"),
        ):
            resp = client.get(f"/api/pickup/{biz.slug}/status/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["unregistered_orders"] == []
        assert data["total_unregistered"] == 0

    def test_minutes_ago_from_iso_timestamp(self, client, db):
        """minutes_ago is computed correctly for ISO string timestamps."""
        from unittest.mock import patch
        from datetime import datetime, timedelta, timezone
        biz, sp = self._pos_biz(db, slug="pos-biz-5")
        _login(client, biz, sp)
        ten_mins_ago = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        order = {**_FAKE_POS_ORDER, "id": "POS-ISO", "created_at": ten_mins_ago}
        with patch(
            "notifications.pos_integration.POSIntegration.get_recent_orders",
            return_value=[order],
        ):
            resp = client.get(f"/api/pickup/{biz.slug}/status/")
        item = resp.json()["unregistered_orders"][0]
        assert item["minutes_ago"] is not None
        assert 9 <= item["minutes_ago"] <= 11  # allow 1 min clock skew

    def test_minutes_ago_from_ms_timestamp(self, client, db):
        """minutes_ago is computed correctly for millisecond epoch timestamps (Clover)."""
        from unittest.mock import patch
        from datetime import datetime, timedelta, timezone
        import time
        biz, sp = self._pos_biz(db, slug="pos-biz-6")
        _login(client, biz, sp)
        five_mins_ago_ms = int(
            (datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp() * 1000
        )
        order = {**_FAKE_POS_ORDER, "id": "POS-MS", "created_at": five_mins_ago_ms}
        with patch(
            "notifications.pos_integration.POSIntegration.get_recent_orders",
            return_value=[order],
        ):
            resp = client.get(f"/api/pickup/{biz.slug}/status/")
        item = resp.json()["unregistered_orders"][0]
        assert item["minutes_ago"] is not None
        assert 4 <= item["minutes_ago"] <= 6

    def test_response_shape_includes_new_keys(self, client, pickup_business, pickup_staff):
        """Existing callers get unregistered_orders and total_unregistered even with no POS."""
        _login(client, pickup_business, pickup_staff)
        resp = client.get(f"/api/pickup/{pickup_business.slug}/status/")
        data = resp.json()
        assert "unregistered_orders" in data
        assert "total_unregistered" in data
        assert isinstance(data["unregistered_orders"], list)

    def test_unregistered_order_includes_total_and_reference(self, client, db):
        """unregistered_orders items include order_total and order_reference."""
        from unittest.mock import patch
        biz, sp = self._pos_biz(db, slug="pos-biz-7")
        _login(client, biz, sp)
        order_with_total = {
            **_FAKE_POS_ORDER,
            "id": "POS-FULL",
            "order_total": 1250,
            "order_reference": "R-42",
        }
        with patch(
            "notifications.pos_integration.POSIntegration.get_recent_orders",
            return_value=[order_with_total],
        ):
            resp = client.get(f"/api/pickup/{biz.slug}/status/")
        item = resp.json()["unregistered_orders"][0]
        assert item["order_total"] == 1250
        assert item["order_reference"] == "R-42"


class TestPickupStatusAPIAnalyticsFields:
    """active_orders response includes pos_order_created_at, pos_order_total, pos_order_reference."""

    def test_active_order_includes_pos_analytics_fields(self, client, pickup_business, pickup_staff):
        from django.utils import timezone
        _login(client, pickup_business, pickup_staff)
        entry = PickupService.register(pickup_business, order_number="X1", customer_name="Eve")
        # Set analytics fields manually (as the POS-confirm path would)
        ts = timezone.now()
        entry.pos_order_created_at = ts
        entry.pos_order_total = 750
        entry.pos_order_reference = "R-99"
        entry.save(update_fields=["pos_order_created_at", "pos_order_total", "pos_order_reference"])

        resp = client.get(f"/api/pickup/{pickup_business.slug}/status/")
        data = resp.json()
        order = data["active_orders"][0]
        assert order["pos_order_created_at"] is not None
        assert order["pos_order_total"] == 750
        assert order["pos_order_reference"] == "R-99"

    def test_active_order_nulls_when_no_pos(self, client, pickup_business, pickup_staff):
        """When no POS match, analytics fields are null/empty."""
        _login(client, pickup_business, pickup_staff)
        PickupService.register(pickup_business, order_number="X2")
        resp = client.get(f"/api/pickup/{pickup_business.slug}/status/")
        order = resp.json()["active_orders"][0]
        assert order["pos_order_created_at"] is None
        assert order["pos_order_total"] is None
        assert order["pos_order_reference"] == ""


# ---------------------------------------------------------------------------
# Phase 25: Auto-registration of POS orders that have a phone number
# ---------------------------------------------------------------------------

_POS_ORDER_WITH_PHONE = {
    "id": "SQ-PHONE-001",
    "customer_name": "Jordan Lee",
    "items": ["Steak Frites", "Still Water"],
    "created_at": "2026-05-17T10:00:00+00:00",
    "phone": "+16135559911",
    "order_total": 2400,
    "order_reference": "T-55",
}

_POS_ORDER_NO_PHONE = {
    "id": "SQ-NOPHONE-001",
    "customer_name": "Anonymous",
    "items": ["Coffee"],
    "created_at": "2026-05-17T10:05:00+00:00",
    "phone": "",
    "order_total": 350,
    "order_reference": "T-56",
}


class TestPickupAutoRegistration:
    """Phase 25: POS orders with a phone are auto-registered into Section 1."""

    def _pos_biz(self, db, slug="auto-reg-biz"):
        biz = Business.objects.create(
            name="Auto Café",
            slug=slug,
            is_active=True,
            queue_enabled=False,
            pickup_enabled=True,
            pos_type="square",
            pos_api_token="tok",
            pos_merchant_id="mid",
        )
        sp = StaffPhone.objects.create(phone="+16135550070", business=biz, name="Staff")
        return biz, sp

    def test_phone_order_auto_registered_in_section1(self, client, db):
        """POS order with phone → appears in active_orders (Section 1)."""
        from unittest.mock import patch
        biz, sp = self._pos_biz(db)
        _login(client, biz, sp)
        with patch(
            "notifications.pos_integration.POSIntegration.get_recent_orders",
            return_value=[_POS_ORDER_WITH_PHONE],
        ):
            resp = client.get(f"/api/pickup/{biz.slug}/status/")
        data = resp.json()
        assert data["total_active"] == 1
        assert data["active_orders"][0]["order_number"] == "T-55"
        assert data["active_orders"][0]["customer_name"] == "Jordan Lee"

    def test_phone_order_excluded_from_section2(self, client, db):
        """POS order with phone → NOT in unregistered_orders (Section 2)."""
        from unittest.mock import patch
        biz, sp = self._pos_biz(db, slug="auto-reg-biz-2")
        _login(client, biz, sp)
        with patch(
            "notifications.pos_integration.POSIntegration.get_recent_orders",
            return_value=[_POS_ORDER_WITH_PHONE],
        ):
            resp = client.get(f"/api/pickup/{biz.slug}/status/")
        data = resp.json()
        assert data["total_unregistered"] == 0
        assert data["unregistered_orders"] == []

    def test_no_phone_order_stays_in_section2(self, client, db):
        """POS order without phone → stays in unregistered_orders (Section 2)."""
        from unittest.mock import patch
        biz, sp = self._pos_biz(db, slug="auto-reg-biz-3")
        _login(client, biz, sp)
        with patch(
            "notifications.pos_integration.POSIntegration.get_recent_orders",
            return_value=[_POS_ORDER_NO_PHONE],
        ):
            resp = client.get(f"/api/pickup/{biz.slug}/status/")
        data = resp.json()
        assert data["total_unregistered"] == 1
        assert data["total_active"] == 0

    def test_mixed_orders_split_correctly(self, client, db):
        """One order with phone → Section 1; one without → Section 2."""
        from unittest.mock import patch
        biz, sp = self._pos_biz(db, slug="auto-reg-biz-4")
        _login(client, biz, sp)
        with patch(
            "notifications.pos_integration.POSIntegration.get_recent_orders",
            return_value=[_POS_ORDER_WITH_PHONE, _POS_ORDER_NO_PHONE],
        ):
            resp = client.get(f"/api/pickup/{biz.slug}/status/")
        data = resp.json()
        assert data["total_active"] == 1
        assert data["total_unregistered"] == 1

    def test_auto_registered_entry_persisted_in_db(self, client, db):
        """Auto-registration creates a real PickupEntry with all POS fields stamped."""
        from unittest.mock import patch
        biz, sp = self._pos_biz(db, slug="auto-reg-biz-5")
        _login(client, biz, sp)
        with patch(
            "notifications.pos_integration.POSIntegration.get_recent_orders",
            return_value=[_POS_ORDER_WITH_PHONE],
        ):
            client.get(f"/api/pickup/{biz.slug}/status/")

        entry = PickupEntry.objects.get(business=biz)
        assert entry.phone == "+16135559911"
        assert entry.pos_order_id == "SQ-PHONE-001"
        assert entry.pos_order_items == ["Steak Frites", "Still Water"]
        assert entry.pos_order_total == 2400
        assert entry.pos_order_reference == "T-55"
        assert entry.status == PickupEntry.Status.WAITING

    def test_auto_registered_only_once_on_repeated_polls(self, client, db):
        """Polling repeatedly does not create duplicate PickupEntries."""
        from unittest.mock import patch
        biz, sp = self._pos_biz(db, slug="auto-reg-biz-6")
        _login(client, biz, sp)
        with patch(
            "notifications.pos_integration.POSIntegration.get_recent_orders",
            return_value=[_POS_ORDER_WITH_PHONE],
        ):
            client.get(f"/api/pickup/{biz.slug}/status/")
            client.get(f"/api/pickup/{biz.slug}/status/")
            client.get(f"/api/pickup/{biz.slug}/status/")

        assert PickupEntry.objects.filter(business=biz).count() == 1

    def test_pos_analytics_on_auto_registered_entry(self, client, db):
        """active_orders for auto-registered entry includes pos_order_created_at."""
        from unittest.mock import patch
        biz, sp = self._pos_biz(db, slug="auto-reg-biz-7")
        _login(client, biz, sp)
        with patch(
            "notifications.pos_integration.POSIntegration.get_recent_orders",
            return_value=[_POS_ORDER_WITH_PHONE],
        ):
            resp = client.get(f"/api/pickup/{biz.slug}/status/")
        order = resp.json()["active_orders"][0]
        assert order["pos_order_created_at"] is not None
        assert order["pos_order_total"] == 2400
        assert order["pos_order_reference"] == "T-55"
