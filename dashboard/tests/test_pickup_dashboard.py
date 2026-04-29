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
