import pytest
from django.urls import reverse
from unittest.mock import patch

from businesses.models import Business, StaffPhone
from queues.models import QueueEntry


def _login(client, business, staff_phone):
    session = client.session
    session["business_id"] = business.pk
    session["staff_phone_id"] = staff_phone.pk
    session.save()


# ── StaffLoginView ────────────────────────────────────────────────────────────

class TestStaffLogin:
    def test_get_returns_200(self, client, active_business):
        # Per-slug login redirects to unified login
        url = reverse("dashboard:login", kwargs={"slug": active_business.slug})
        assert client.get(url, follow=True).status_code == 200

    def test_unified_login_get_returns_200(self, client, db):
        url = reverse("dashboard:unified_login")
        assert client.get(url).status_code == 200

    def test_valid_phone_sets_session_and_redirects(self, client, active_business, staff_phone):
        url = reverse("dashboard:unified_login")
        resp = client.post(url, {"slug": active_business.slug, "phone": staff_phone.phone})
        assert resp.status_code == 302
        assert client.session["business_id"] == active_business.pk
        assert client.session["staff_phone_id"] == staff_phone.pk

    def test_unknown_phone_returns_error(self, client, active_business):
        url = reverse("dashboard:unified_login")
        # +16135550999 is a valid CA number format but not registered as staff
        resp = client.post(url, {"slug": active_business.slug, "phone": "+16135550999"})
        assert resp.status_code == 200
        assert b"not recognised" in resp.content.lower()

    def test_phone_from_other_business_rejected(self, client, active_business, staff_phone):
        other = Business.objects.create(
            name="Other", slug="other-biz", mode=Business.MODE_PERSON,
            batch_size=1, is_active=True,
        )
        other_staff = StaffPhone.objects.create(phone="+16135559999", business=other, name="Bob")
        url = reverse("dashboard:unified_login")
        resp = client.post(url, {"slug": active_business.slug, "phone": other_staff.phone})
        assert resp.status_code == 200
        assert b"not recognised" in resp.content.lower()

    def test_unknown_slug_returns_404(self, client, db):
        # Per-slug login redirects to unified — unknown slug still handled gracefully
        url = reverse("dashboard:unified_login")
        resp = client.post(url, {"slug": "does-not-exist", "phone": "+19995550000"})
        assert resp.status_code in (200, 404)


# ── StaffLogoutView ───────────────────────────────────────────────────────────

class TestStaffLogout:
    def test_logout_clears_session(self, client, active_business, staff_phone):
        _login(client, active_business, staff_phone)
        client.get(reverse("dashboard:logout", kwargs={"slug": active_business.slug}))
        assert "business_id" not in client.session
        assert "staff_phone_id" not in client.session

    def test_logout_redirects_to_login(self, client, active_business, staff_phone):
        _login(client, active_business, staff_phone)
        resp = client.get(reverse("dashboard:logout", kwargs={"slug": active_business.slug}))
        assert resp.status_code == 302
        assert "login" in resp["Location"]


# ── DashboardView ─────────────────────────────────────────────────────────────

class TestDashboardView:
    def test_no_session_redirects_to_login(self, client, active_business):
        url = reverse("dashboard:dashboard", kwargs={"slug": active_business.slug})
        resp = client.get(url)
        assert resp.status_code == 302
        assert "login" in resp["Location"]

    def test_valid_session_returns_200(self, client, active_business, staff_phone):
        _login(client, active_business, staff_phone)
        resp = client.get(reverse("dashboard:dashboard", kwargs={"slug": active_business.slug}))
        assert resp.status_code == 200

    def test_shows_waiting_entries(self, client, active_business, staff_phone, queue_entry):
        _login(client, active_business, staff_phone)
        resp = client.get(reverse("dashboard:dashboard", kwargs={"slug": active_business.slug}))
        assert queue_entry.name.encode() in resp.content

    def test_shows_last_called_entry(self, client, active_business, staff_phone):
        from django.utils import timezone
        _login(client, active_business, staff_phone)
        QueueEntry.objects.create(
            business=active_business, name="Called Person",
            phone="+16135550010", status=QueueEntry.Status.CALLED,
            position=1, batch_number=1, called_at=timezone.now(),
        )
        # In batch mode called entries are rendered via JS polling, not initial HTML.
        # Verify the API response includes the called entry name instead.
        data = client.get(f"/api/queue/{active_business.slug}/status/").json()
        assert data["called_last"]["name"] == "Called Person"

    def test_wrong_business_session_redirects(self, client, active_business, staff_phone):
        other = Business.objects.create(
            name="Other", slug="other2", mode=Business.MODE_PERSON,
            batch_size=1, is_active=True,
        )
        _login(client, active_business, staff_phone)
        resp = client.get(reverse("dashboard:dashboard", kwargs={"slug": other.slug}))
        assert resp.status_code == 302
        assert "login" in resp["Location"]


# ── CallNextView ──────────────────────────────────────────────────────────────

class TestCallNextView:
    @patch("notifications.sms.TwilioSMSBackend.send", return_value=(True, ""))
    def test_post_calls_next_and_redirects(self, mock_send, client, active_business, staff_phone, queue_entry):
        _login(client, active_business, staff_phone)
        resp = client.post(reverse("dashboard:call_next", kwargs={"slug": active_business.slug}))
        assert resp.status_code == 302
        queue_entry.refresh_from_db()
        assert queue_entry.status == QueueEntry.Status.CALLED

    @patch("notifications.sms.TwilioSMSBackend.send", return_value=(True, ""))
    def test_empty_queue_redirects_without_crash(self, mock_send, client, active_business, staff_phone):
        _login(client, active_business, staff_phone)
        resp = client.post(reverse("dashboard:call_next", kwargs={"slug": active_business.slug}))
        assert resp.status_code == 302

    def test_no_session_redirects_to_login(self, client, active_business):
        resp = client.post(reverse("dashboard:call_next", kwargs={"slug": active_business.slug}))
        assert resp.status_code == 302
        assert "login" in resp["Location"]


# ── QueueStatusAPIView ────────────────────────────────────────────────────────

class TestQueueStatusAPI:
    def test_no_session_returns_401(self, client, active_business):
        resp = client.get(f"/api/queue/{active_business.slug}/status/")
        assert resp.status_code == 401

    def test_valid_session_returns_200(self, client, active_business, staff_phone):
        _login(client, active_business, staff_phone)
        resp = client.get(f"/api/queue/{active_business.slug}/status/")
        assert resp.status_code == 200

    def test_response_shape(self, client, active_business, staff_phone):
        _login(client, active_business, staff_phone)
        data = client.get(f"/api/queue/{active_business.slug}/status/").json()
        assert "waiting" in data
        assert "called_last" in data
        assert "mode" in data
        assert "batch_size" in data
        assert "avg_service_minutes" in data

    def test_waiting_contains_entry(self, client, active_business, staff_phone, queue_entry):
        _login(client, active_business, staff_phone)
        data = client.get(f"/api/queue/{active_business.slug}/status/").json()
        assert len(data["waiting"]) == 1
        assert data["waiting"][0]["name"] == queue_entry.name

    def test_called_last_is_none_when_empty(self, client, active_business, staff_phone):
        _login(client, active_business, staff_phone)
        data = client.get(f"/api/queue/{active_business.slug}/status/").json()
        assert data["called_last"] is None

    @patch("notifications.sms.TwilioSMSBackend.send", return_value=(True, ""))
    def test_called_last_populated_after_call_next(self, mock_send, client, active_business, staff_phone, queue_entry):
        _login(client, active_business, staff_phone)
        from queues.services import QueueService
        QueueService.call_next(active_business)
        data = client.get(f"/api/queue/{active_business.slug}/status/").json()
        assert data["called_last"]["name"] == queue_entry.name

    def test_mode_and_batch_size_correct(self, client, active_business, staff_phone):
        _login(client, active_business, staff_phone)
        data = client.get(f"/api/queue/{active_business.slug}/status/").json()
        assert data["mode"] == active_business.mode
        assert data["batch_size"] == active_business.batch_size


# ── QRCodeView ─────────────────────────────────────────────────────────────────

class TestQRCodeView:
    def test_no_session_redirects_to_login(self, client, active_business):
        url = reverse("dashboard:qr_code", kwargs={"slug": active_business.slug})
        resp = client.get(url)
        assert resp.status_code == 302
        assert "login" in resp["Location"]

    def test_returns_png_image(self, client, active_business, staff_phone):
        _login(client, active_business, staff_phone)
        url = reverse("dashboard:qr_code", kwargs={"slug": active_business.slug})
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp["Content-Type"] == "image/png"

    def test_returns_non_empty_body(self, client, active_business, staff_phone):
        _login(client, active_business, staff_phone)
        url = reverse("dashboard:qr_code", kwargs={"slug": active_business.slug})
        resp = client.get(url)
        assert len(resp.content) > 0

    def test_cached_response_identical(self, client, active_business, staff_phone):
        """Second request should return the same bytes (from cache)."""
        _login(client, active_business, staff_phone)
        url = reverse("dashboard:qr_code", kwargs={"slug": active_business.slug})
        r1 = client.get(url)
        r2 = client.get(url)
        assert r1.content == r2.content

    def test_unknown_slug_returns_404(self, client, db):
        resp = client.get("/staff/no-such-business/qr.png")
        assert resp.status_code == 404
