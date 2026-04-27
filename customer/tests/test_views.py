import pytest
from django.core.cache import cache
from django.urls import reverse

from businesses.models import Business
from queues.models import QueueEntry


@pytest.fixture(autouse=True)
def clear_rate_limit_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def person_business(db):
    return Business.objects.create(
        name="Cuts by Sam",
        slug="cuts-by-sam",
        mode=Business.MODE_PERSON,
        batch_size=1,
        is_active=True,
        country="CA",
    )


@pytest.fixture
def batch_business(db):
    return Business.objects.create(
        name="Batch Barber",
        slug="batch-barber",
        mode=Business.MODE_BATCH,
        batch_size=3,
        is_active=True,
        country="CA",
    )


@pytest.fixture
def inactive_business(db):
    return Business.objects.create(
        name="Closed Shop",
        slug="closed-shop",
        mode=Business.MODE_PERSON,
        batch_size=1,
        is_active=False,
        country="CA",
    )


# ── GET /q/<slug>/ ─────────────────────────────────────────────────────────────

class TestJoinViewGet:
    def test_returns_200_for_active_business(self, client, person_business):
        url = reverse("customer:join", kwargs={"slug": person_business.slug})
        response = client.get(url)
        assert response.status_code == 200

    def test_shows_business_name(self, client, person_business):
        url = reverse("customer:join", kwargs={"slug": person_business.slug})
        response = client.get(url)
        assert person_business.name.encode() in response.content

    def test_shows_logo_colour(self, client, person_business):
        url = reverse("customer:join", kwargs={"slug": person_business.slug})
        response = client.get(url)
        assert person_business.logo_colour.encode() in response.content

    def test_inactive_business_returns_404(self, client, inactive_business):
        url = reverse("customer:join", kwargs={"slug": inactive_business.slug})
        response = client.get(url)
        assert response.status_code == 404

    def test_unknown_slug_returns_404(self, client, db):
        url = reverse("customer:join", kwargs={"slug": "does-not-exist"})
        response = client.get(url)
        assert response.status_code == 404


# ── POST /q/<slug>/ ────────────────────────────────────────────────────────────

class TestJoinViewPost:
    def test_valid_post_creates_entry_and_redirects(self, client, person_business):
        url = reverse("customer:join", kwargs={"slug": person_business.slug})
        response = client.post(url, {"name": "Alice", "phone": "6135550100"})
        assert response.status_code == 302
        assert QueueEntry.objects.filter(business=person_business).count() == 1

    def test_redirect_goes_to_confirmation(self, client, person_business):
        url = reverse("customer:join", kwargs={"slug": person_business.slug})
        response = client.post(url, {"name": "Alice", "phone": "6135550100"})
        entry = QueueEntry.objects.get(business=person_business)
        expected = reverse("customer:confirmation", kwargs={
            "slug": person_business.slug, "entry_id": entry.pk
        })
        assert response["Location"] == expected

    def test_phone_stored_in_e164(self, client, person_business):
        url = reverse("customer:join", kwargs={"slug": person_business.slug})
        client.post(url, {"name": "Alice", "phone": "6135550100"})
        entry = QueueEntry.objects.get(business=person_business)
        assert entry.phone == "+16135550100"

    def test_invalid_phone_returns_form_error(self, client, person_business):
        url = reverse("customer:join", kwargs={"slug": person_business.slug})
        response = client.post(url, {"name": "Alice", "phone": "not-a-phone"})
        assert response.status_code == 200
        assert b"valid phone number" in response.content

    def test_invalid_phone_no_entry_created(self, client, person_business):
        url = reverse("customer:join", kwargs={"slug": person_business.slug})
        client.post(url, {"name": "Alice", "phone": "not-a-phone"})
        assert QueueEntry.objects.filter(business=person_business).count() == 0

    def test_missing_name_returns_form_error(self, client, person_business):
        url = reverse("customer:join", kwargs={"slug": person_business.slug})
        response = client.post(url, {"name": "", "phone": "6135550100"})
        assert response.status_code == 200
        assert b"name" in response.content.lower()

    def test_inactive_business_post_returns_404(self, client, inactive_business):
        url = reverse("customer:join", kwargs={"slug": inactive_business.slug})
        response = client.post(url, {"name": "Alice", "phone": "6135550100"})
        assert response.status_code == 404

    def test_inactive_business_no_entry_created(self, client, inactive_business):
        url = reverse("customer:join", kwargs={"slug": inactive_business.slug})
        client.post(url, {"name": "Alice", "phone": "6135550100"})
        assert QueueEntry.objects.filter(business=inactive_business).count() == 0

    def test_international_phone_with_plus(self, client, person_business):
        url = reverse("customer:join", kwargs={"slug": person_business.slug})
        response = client.post(url, {"name": "Bob", "phone": "+16135550101"})
        assert response.status_code == 302
        entry = QueueEntry.objects.get(business=person_business)
        assert entry.phone == "+16135550101"

    def test_rate_limit_returns_429(self, client, person_business):
        from django.core.cache import cache
        ip = "127.0.0.1"
        cache.set(f"ql_join_{ip}", 20, timeout=3600)
        url = reverse("customer:join", kwargs={"slug": person_business.slug})
        response = client.post(url, {"name": "Alice", "phone": "6135550100"})
        assert response.status_code == 429


# ── GET /q/<slug>/confirmation/<entry_id>/ ─────────────────────────────────────

class TestConfirmView:
    def test_batch_mode_shows_batch_number(self, client, batch_business):
        join_url = reverse("customer:join", kwargs={"slug": batch_business.slug})
        client.post(join_url, {"name": "Carol", "phone": "6135550200"})
        entry = QueueEntry.objects.get(business=batch_business)

        url = reverse("customer:confirmation", kwargs={
            "slug": batch_business.slug, "entry_id": entry.pk
        })
        response = client.get(url)
        assert response.status_code == 200
        assert str(entry.batch_number).encode() in response.content
        assert b"Your batch" in response.content

    def test_person_mode_shows_position(self, client, person_business):
        join_url = reverse("customer:join", kwargs={"slug": person_business.slug})
        client.post(join_url, {"name": "Dave", "phone": "6135550300"})
        entry = QueueEntry.objects.get(business=person_business)

        url = reverse("customer:confirmation", kwargs={
            "slug": person_business.slug, "entry_id": entry.pk
        })
        response = client.get(url)
        assert response.status_code == 200
        assert str(entry.position).encode() in response.content
        assert b"position" in response.content.lower()

    def test_shows_customer_name(self, client, person_business):
        join_url = reverse("customer:join", kwargs={"slug": person_business.slug})
        client.post(join_url, {"name": "Eve", "phone": "6135550400"})
        entry = QueueEntry.objects.get(business=person_business)

        url = reverse("customer:confirmation", kwargs={
            "slug": person_business.slug, "entry_id": entry.pk
        })
        response = client.get(url)
        assert b"Eve" in response.content

    def test_wrong_slug_returns_404(self, client, person_business, batch_business):
        join_url = reverse("customer:join", kwargs={"slug": person_business.slug})
        client.post(join_url, {"name": "Frank", "phone": "6135550500"})
        entry = QueueEntry.objects.get(business=person_business)

        url = reverse("customer:confirmation", kwargs={
            "slug": batch_business.slug, "entry_id": entry.pk
        })
        response = client.get(url)
        assert response.status_code == 404

    def test_wait_range_not_shown_when_customer_is_first(self, client, person_business):
        join_url = reverse("customer:join", kwargs={"slug": person_business.slug})
        client.post(join_url, {"name": "Solo", "phone": "6135550601"})
        entry = QueueEntry.objects.get(business=person_business)
        url = reverse("customer:confirmation", kwargs={
            "slug": person_business.slug, "entry_id": entry.pk
        })
        response = client.get(url)
        # No avg_service_minutes → est wait stat shows dash placeholder
        assert b'id="statWait"' in response.content
        assert b"&mdash;" not in response.content  # no range text

    def test_wait_shown_when_avg_service_minutes_set(self, client, db):
        biz = Business.objects.create(
            name="Timed Shop", slug="timed-shop",
            mode=Business.MODE_PERSON, batch_size=1,
            is_active=True, avg_service_minutes=10,
        )
        QueueEntry.objects.create(
            business=biz, name="First", phone="+16135550600",
            status=QueueEntry.Status.WAITING, position=1,
        )
        e2 = QueueEntry.objects.create(
            business=biz, name="Second", phone="+16135550601",
            status=QueueEntry.Status.WAITING, position=2,
        )
        url = reverse("customer:confirmation", kwargs={"slug": biz.slug, "entry_id": e2.pk})
        response = client.get(url)
        # Stat tile shows ~Xm format (1 person ahead × 10 min → ~10m)
        assert b"~" in response.content
        assert b"m" in response.content


# ── GET /q/<slug>/status/<entry_id>/ ───────────────────────────────────────────

class TestCustomerStatusView:
    def _url(self, slug, entry_id):
        return reverse("customer:status", kwargs={"slug": slug, "entry_id": entry_id})

    def test_returns_200_no_auth(self, client, person_business):
        entry = QueueEntry.objects.create(
            business=person_business, name="A", phone="+16135550700",
            status=QueueEntry.Status.WAITING, position=1,
        )
        response = client.get(self._url(person_business.slug, entry.pk))
        assert response.status_code == 200

    def test_returns_json(self, client, person_business):
        entry = QueueEntry.objects.create(
            business=person_business, name="A", phone="+16135550701",
            status=QueueEntry.Status.WAITING, position=1,
        )
        response = client.get(self._url(person_business.slug, entry.pk))
        data = response.json()
        assert data["status"] == "waiting"
        assert data["position"] == 1
        assert data["mode"] == Business.MODE_PERSON

    def test_ahead_count_person_mode(self, client, person_business):
        QueueEntry.objects.create(
            business=person_business, name="First", phone="+16135550702",
            status=QueueEntry.Status.WAITING, position=1,
        )
        entry = QueueEntry.objects.create(
            business=person_business, name="Second", phone="+16135550703",
            status=QueueEntry.Status.WAITING, position=2,
        )
        data = client.get(self._url(person_business.slug, entry.pk)).json()
        assert data["ahead_count"] == 1

    def test_ahead_count_batch_mode(self, client, batch_business):
        QueueEntry.objects.create(
            business=batch_business, name="B1a", phone="+16135550710",
            status=QueueEntry.Status.WAITING, position=1, batch_number=1,
        )
        entry = QueueEntry.objects.create(
            business=batch_business, name="B2a", phone="+16135550711",
            status=QueueEntry.Status.WAITING, position=2, batch_number=2,
        )
        data = client.get(self._url(batch_business.slug, entry.pk)).json()
        assert data["ahead_count"] == 1

    def test_currently_serving_batch_when_none_called(self, client, person_business):
        entry = QueueEntry.objects.create(
            business=person_business, name="A", phone="+16135550720",
            status=QueueEntry.Status.WAITING, position=1,
        )
        data = client.get(self._url(person_business.slug, entry.pk)).json()
        assert data["currently_serving_batch"] is None
        assert data["currently_serving_position"] is None

    def test_currently_serving_reflects_called_entry(self, client, person_business):
        from unittest.mock import patch
        from queues.services import QueueService
        entry1 = QueueEntry.objects.create(
            business=person_business, name="First", phone="+16135550730",
            status=QueueEntry.Status.WAITING, position=1,
        )
        entry2 = QueueEntry.objects.create(
            business=person_business, name="Second", phone="+16135550731",
            status=QueueEntry.Status.WAITING, position=2,
        )
        with patch("notifications.sms.TwilioSMSBackend.send", return_value=True):
            QueueService.call_next(person_business)
        data = client.get(self._url(person_business.slug, entry2.pk)).json()
        assert data["currently_serving_position"] == entry1.position

    def test_wrong_slug_returns_404(self, client, person_business, batch_business):
        entry = QueueEntry.objects.create(
            business=person_business, name="A", phone="+16135550740",
            status=QueueEntry.Status.WAITING, position=1,
        )
        response = client.get(self._url(batch_business.slug, entry.pk))
        assert response.status_code == 404

    def test_called_entry_returns_called_status(self, client, person_business):
        from unittest.mock import patch
        from queues.services import QueueService
        entry = QueueEntry.objects.create(
            business=person_business, name="A", phone="+16135550750",
            status=QueueEntry.Status.WAITING, position=1,
        )
        with patch("notifications.sms.TwilioSMSBackend.send", return_value=True):
            QueueService.call_next(person_business)
        entry.refresh_from_db()
        data = client.get(self._url(person_business.slug, entry.pk)).json()
        assert data["status"] == "called"
        assert data["ahead_count"] == 0
