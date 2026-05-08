"""Tests for notifications.pos_integration — POSIntegration, Clover, Square."""
import json
from unittest.mock import MagicMock, patch

import pytest

from notifications.pos_integration import (
    CloverIntegration,
    POSIntegration,
    SquareIntegration,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_business(pos_type="clover", token="tok", merchant_id="MERCH"):
    b = MagicMock()
    b.pos_type = pos_type
    b.pos_api_token = token
    b.pos_merchant_id = merchant_id
    b.POS_NONE = "none"
    b.POS_CLOVER = "clover"
    b.POS_SQUARE = "square"
    b.slug = "test-biz"
    return b


CLOVER_RESPONSE = {
    "elements": [
        {
            "id": "order-1",
            "note": "Ahmed",
            "createdTime": 1700000000000,
            "lineItems": {
                "elements": [
                    {"name": "Pistachio Latte"},
                    {"name": "Blueberry Muffin"},
                ]
            },
        },
        {
            "id": "order-2",
            "note": "Sara",
            "createdTime": 1700000100000,
            "lineItems": {"elements": [{"name": "Cappuccino"}]},
        },
        # No customer name — should be excluded
        {
            "id": "order-3",
            "note": "",
            "title": "",
            "createdTime": 1700000200000,
            "lineItems": {"elements": []},
        },
    ]
}

SQUARE_RESPONSE = {
    "orders": [
        {
            "id": "sq-order-1",
            "ticket_name": "Mohamed",
            "created_at": "2024-01-01T12:00:00Z",
            "line_items": [
                {"name": "Flat White"},
                {"name": "Croissant"},
            ],
        },
        {
            "id": "sq-order-2",
            "ticket_name": "",
            "fulfillments": [
                {
                    "pickup_details": {
                        "recipient": {"display_name": "Lina"}
                    }
                }
            ],
            "created_at": "2024-01-01T12:05:00Z",
            "line_items": [{"name": "Green Tea"}],
        },
    ]
}


# ---------------------------------------------------------------------------
# CloverIntegration
# ---------------------------------------------------------------------------

class TestCloverIntegration:
    def test_returns_normalised_orders(self):
        biz = _make_business()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = CLOVER_RESPONSE

        with patch("notifications.pos_integration.CloverIntegration") as _:
            import requests as req
            with patch.object(req, "get", return_value=mock_resp):
                orders = CloverIntegration.get_orders(biz)

        assert len(orders) == 2
        assert orders[0]["id"] == "order-1"
        assert orders[0]["customer_name"] == "Ahmed"
        assert "Pistachio Latte" in orders[0]["items"]
        assert "Blueberry Muffin" in orders[0]["items"]
        assert orders[1]["customer_name"] == "Sara"

    def test_returns_empty_on_api_error(self):
        biz = _make_business()
        mock_resp = MagicMock()
        mock_resp.status_code = 401

        with patch("requests.get", return_value=mock_resp):
            orders = CloverIntegration.get_orders(biz)

        assert orders == []

    def test_returns_empty_on_network_exception(self):
        biz = _make_business()
        with patch("requests.get", side_effect=Exception("timeout")):
            orders = CloverIntegration.get_orders(biz)
        assert orders == []


# ---------------------------------------------------------------------------
# SquareIntegration
# ---------------------------------------------------------------------------

class TestSquareIntegration:
    def test_returns_normalised_orders_from_ticket_name(self):
        biz = _make_business(pos_type="square")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SQUARE_RESPONSE

        with patch("requests.post", return_value=mock_resp):
            orders = SquareIntegration.get_orders(biz)

        assert len(orders) == 2
        assert orders[0]["id"] == "sq-order-1"
        assert orders[0]["customer_name"] == "Mohamed"
        assert "Flat White" in orders[0]["items"]

    def test_falls_back_to_fulfillment_recipient(self):
        biz = _make_business(pos_type="square")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SQUARE_RESPONSE

        with patch("requests.post", return_value=mock_resp):
            orders = SquareIntegration.get_orders(biz)

        assert orders[1]["customer_name"] == "Lina"

    def test_returns_empty_on_api_error(self):
        biz = _make_business(pos_type="square")
        mock_resp = MagicMock()
        mock_resp.status_code = 403

        with patch("requests.post", return_value=mock_resp):
            orders = SquareIntegration.get_orders(biz)

        assert orders == []


# ---------------------------------------------------------------------------
# POSIntegration.match_customer
# ---------------------------------------------------------------------------

ORDERS = [
    {"id": "o1", "customer_name": "Ahmed", "items": ["Pistachio Latte", "Muffin"], "created_at": None},
    {"id": "o2", "customer_name": "Sara",  "items": ["Cappuccino"],                "created_at": None},
    {"id": "o3", "customer_name": "Mohamed Al Rashid", "items": ["Espresso"],      "created_at": None},
]


class TestPOSIntegrationMatchCustomer:
    def _match(self, name, orders=None):
        biz = _make_business()
        use = ORDERS if orders is None else orders
        with patch.object(POSIntegration, "get_recent_orders", return_value=use):
            return POSIntegration.match_customer(biz, name)

    def test_exact_match(self):
        result = self._match("Ahmed")
        assert result["matched"] is True
        assert result["order_id"] == "o1"
        assert "Pistachio Latte" in result["order_items"]
        assert result["confidence"] >= 0.75

    def test_case_insensitive(self):
        result = self._match("ahmed")
        assert result["matched"] is True
        assert result["order_id"] == "o1"

    def test_full_name_match(self):
        # Full name match (all tokens present) should hit threshold
        result = self._match("Mohamed Al Rashid")
        assert result["matched"] is True
        assert result["order_id"] == "o3"

    def test_reversed_name_match(self):
        # token_sort_ratio handles name order reversal
        result = self._match("Al Rashid Mohamed")
        assert result["matched"] is True
        assert result["order_id"] == "o3"

    def test_low_confidence_no_match(self):
        result = self._match("Xyz Zzz Qqq")
        assert result["matched"] is False
        assert result["order_id"] is None

    def test_empty_name_returns_no_match(self):
        result = self._match("")
        assert result["matched"] is False

    def test_no_orders_returns_no_match(self):
        result = self._match("Ahmed", orders=[])
        assert result["matched"] is False

    def test_returns_none_pos_type(self):
        biz = _make_business(pos_type="none")
        biz.POS_NONE = "none"
        biz.POS_CLOVER = "clover"
        biz.POS_SQUARE = "square"
        with patch.object(POSIntegration, "get_recent_orders", return_value=[]) as mock_get:
            result = POSIntegration.match_customer(biz, "Ahmed")
        assert result["matched"] is False


# ---------------------------------------------------------------------------
# /api/pickup/<slug>/match/ endpoint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPickupMatchAPIView:
    def test_returns_match(self, client, pickup_business):
        with patch.object(POSIntegration, "match_customer", return_value={
            "matched": True, "order_id": "ORD-1",
            "order_items": ["Latte"], "confidence": 0.95,
        }):
            resp = client.post(
                f"/api/pickup/{pickup_business.slug}/match/",
                data=json.dumps({"customer_name": "Ahmed"}),
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["matched"] is True
        assert data["order_id"] == "ORD-1"
        assert data["items"] == ["Latte"]

    def test_returns_no_match(self, client, pickup_business):
        with patch.object(POSIntegration, "match_customer", return_value={
            "matched": False, "order_id": None,
            "order_items": [], "confidence": 0.3,
        }):
            resp = client.post(
                f"/api/pickup/{pickup_business.slug}/match/",
                data=json.dumps({"customer_name": "Unknown"}),
                content_type="application/json",
            )
        assert resp.status_code == 200
        assert resp.json()["matched"] is False

    def test_missing_name_returns_400(self, client, pickup_business):
        resp = client.post(
            f"/api/pickup/{pickup_business.slug}/match/",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_invalid_json_returns_400(self, client, pickup_business):
        resp = client.post(
            f"/api/pickup/{pickup_business.slug}/match/",
            data="not-json",
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_no_pos_configured_returns_no_match(self, client, pickup_business):
        pickup_business.pos_type = "none"
        pickup_business.save()
        resp = client.post(
            f"/api/pickup/{pickup_business.slug}/match/",
            data=json.dumps({"customer_name": "Ahmed"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["matched"] is False


@pytest.fixture
def pickup_business(db):
    from businesses.models import Business
    return Business.objects.create(
        name="Test Café",
        slug="test-cafe-pos",
        is_active=True,
        pickup_enabled=True,
        pos_type="clover",
        pos_api_token="test-token",
        pos_merchant_id="MERCH123",
    )
