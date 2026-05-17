"""Tests for notifications.pos_integration — POSIntegration, Clover, Square, Toast, Lightspeed."""
import json
from unittest.mock import MagicMock, patch

import pytest

from notifications.pos_integration import (
    CloverIntegration,
    LightspeedIntegration,
    POSIntegration,
    SquareIntegration,
    ToastIntegration,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_business(pos_type="clover", token="tok", merchant_id="MERCH",
                   toast_client_id="", toast_client_secret=""):
    b = MagicMock()
    b.pos_type = pos_type
    b.pos_api_token = token
    b.pos_merchant_id = merchant_id
    b.toast_client_id = toast_client_id
    b.toast_client_secret = toast_client_secret
    b.POS_NONE = "none"
    b.POS_CLOVER = "clover"
    b.POS_SQUARE = "square"
    b.POS_TOAST = "toast"
    b.POS_LIGHTSPEED = "lightspeed"
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
        """ticket_name is the order reference (ticket number), NOT the customer name."""
        biz = _make_business(pos_type="square")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SQUARE_RESPONSE

        with patch("requests.post", return_value=mock_resp):
            orders = SquareIntegration.get_orders(biz)

        assert len(orders) == 2
        assert orders[0]["id"] == "sq-order-1"
        # ticket_name goes to order_reference, not customer_name
        assert orders[0]["order_reference"] == "Mohamed"
        assert orders[0]["customer_name"] == ""  # no real customer name in this order
        assert "Flat White" in orders[0]["items"]

    def test_customer_name_always_empty(self):
        """Square integration no longer uses fulfillment recipient as customer_name."""
        biz = _make_business(pos_type="square")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SQUARE_RESPONSE

        with patch("requests.post", return_value=mock_resp):
            orders = SquareIntegration.get_orders(biz)

        # customer_name is always empty — phone via Customer API is the identifier
        assert orders[1]["customer_name"] == ""

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


ORDERS_WITH_PHONE = [
    {"id": "o1", "customer_name": "Ahmed",             "items": ["Pistachio Latte", "Muffin"], "created_at": None, "phone": "+14375550001", "order_reference": "101"},
    {"id": "o2", "customer_name": "Sara",              "items": ["Cappuccino"],                "created_at": None, "phone": "+14375550002", "order_reference": "102"},
    {"id": "o3", "customer_name": "Mohamed Al Rashid", "items": ["Espresso"],                 "created_at": None, "phone": "",              "order_reference": "103"},
]


class TestPOSIntegrationMatchCustomer:
    def _match(self, name="", phone="", order_number="", orders=None):
        biz = _make_business()
        use = ORDERS if orders is None else orders
        with patch.object(POSIntegration, "get_recent_orders", return_value=use):
            return POSIntegration.match_customer(
                biz, customer_name=name, phone=phone, order_number=order_number
            )

    def test_exact_match(self):
        result = self._match(name="Ahmed")
        assert result["matched"] is True
        assert result["order_id"] == "o1"
        assert "Pistachio Latte" in result["order_items"]
        assert result["confidence"] >= 0.75

    def test_case_insensitive(self):
        result = self._match(name="ahmed")
        assert result["matched"] is True
        assert result["order_id"] == "o1"

    def test_full_name_match(self):
        # Full name match (all tokens present) should hit threshold
        result = self._match(name="Mohamed Al Rashid")
        assert result["matched"] is True
        assert result["order_id"] == "o3"

    def test_reversed_name_match(self):
        # token_sort_ratio handles name order reversal
        result = self._match(name="Al Rashid Mohamed")
        assert result["matched"] is True
        assert result["order_id"] == "o3"

    def test_low_confidence_no_match(self):
        result = self._match(name="Xyz Zzz Qqq")
        assert result["matched"] is False
        assert result["order_id"] is None

    def test_empty_name_returns_no_match(self):
        result = self._match(name="")
        assert result["matched"] is False

    def test_no_orders_returns_no_match(self):
        result = self._match(name="Ahmed", orders=[])
        assert result["matched"] is False

    def test_returns_none_pos_type(self):
        biz = _make_business(pos_type="none")
        with patch.object(POSIntegration, "get_recent_orders", return_value=[]):
            result = POSIntegration.match_customer(biz, customer_name="Ahmed")
        assert result["matched"] is False

    def test_phone_exact_match(self):
        result = self._match(phone="+14375550001", orders=ORDERS_WITH_PHONE)
        assert result["matched"] is True
        assert result["order_id"] == "o1"
        assert result["confidence"] == 1.0

    def test_phone_beats_name(self):
        # Phone match should win over any name fuzzy match
        result = self._match(name="Sara", phone="+14375550001", orders=ORDERS_WITH_PHONE)
        assert result["matched"] is True
        assert result["order_id"] == "o1"  # phone match for Ahmed, not name match for Sara

    def test_order_number_exact_match(self):
        result = self._match(order_number="102", orders=ORDERS_WITH_PHONE)
        assert result["matched"] is True
        assert result["order_id"] == "o2"
        assert result["confidence"] == 1.0

    def test_order_number_with_hash_prefix(self):
        result = self._match(order_number="#101", orders=ORDERS_WITH_PHONE)
        assert result["matched"] is True
        assert result["order_id"] == "o1"

    def test_no_match_returns_multiple_false(self):
        result = self._match(name="Nobody Here")
        assert result["matched"] is False
        assert result.get("multiple") is False

    def test_response_has_orders_list(self):
        result = self._match(name="Ahmed")
        assert result["matched"] is True
        assert isinstance(result["orders"], list)
        assert len(result["orders"]) >= 1
        first = result["orders"][0]
        assert "order_id" in first
        assert "items" in first
        assert "confidence" in first


# ---------------------------------------------------------------------------
# /api/pickup/<slug>/match/ endpoint
# ---------------------------------------------------------------------------

_FULL_MATCH_RETURN = {
    "matched": True,
    "multiple": False,
    "orders": [{"order_id": "ORD-1", "order_reference": "42", "items": ["Latte"], "confidence": 0.95}],
    "order_id": "ORD-1",
    "order_items": ["Latte"],
    "confidence": 0.95,
}

_NO_MATCH_RETURN = {
    "matched": False,
    "multiple": False,
    "orders": [],
    "order_id": None,
    "order_items": [],
    "confidence": 0.3,
}


@pytest.mark.django_db
class TestPickupMatchAPIView:
    def test_returns_match_by_name(self, client, pickup_business):
        with patch.object(POSIntegration, "match_customer", return_value=_FULL_MATCH_RETURN):
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
        assert "orders" in data
        assert data["orders"][0]["order_reference"] == "42"

    def test_returns_match_by_phone(self, client, pickup_business):
        with patch.object(POSIntegration, "match_customer", return_value=_FULL_MATCH_RETURN):
            resp = client.post(
                f"/api/pickup/{pickup_business.slug}/match/",
                data=json.dumps({"phone": "+14375550001"}),
                content_type="application/json",
            )
        assert resp.status_code == 200
        assert resp.json()["matched"] is True

    def test_returns_match_by_order_number(self, client, pickup_business):
        with patch.object(POSIntegration, "match_customer", return_value=_FULL_MATCH_RETURN):
            resp = client.post(
                f"/api/pickup/{pickup_business.slug}/match/",
                data=json.dumps({"order_number": "42"}),
                content_type="application/json",
            )
        assert resp.status_code == 200
        assert resp.json()["matched"] is True

    def test_returns_no_match(self, client, pickup_business):
        with patch.object(POSIntegration, "match_customer", return_value=_NO_MATCH_RETURN):
            resp = client.post(
                f"/api/pickup/{pickup_business.slug}/match/",
                data=json.dumps({"customer_name": "Unknown"}),
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["matched"] is False
        assert data["orders"] == []

    def test_missing_all_identifiers_returns_400(self, client, pickup_business):
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
        data = resp.json()
        assert data["matched"] is False
        assert data["orders"] == []


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


# ---------------------------------------------------------------------------
# ToastIntegration
# ---------------------------------------------------------------------------

TOAST_RESPONSE = [
    {
        "guid": "toast-order-1",
        "checks": [
            {
                "customer": {"firstName": "Ahmed", "lastName": "Al Rashid"},
                "selections": [
                    {"displayName": "Pistachio Latte"},
                    {"displayName": "Blueberry Muffin"},
                ],
            }
        ],
    },
    {
        "guid": "toast-order-2",
        "checks": [
            {
                "customer": {"firstName": "Sara", "lastName": ""},
                "selections": [{"displayName": "Cappuccino"}],
            }
        ],
    },
    # No customer name — should be excluded
    {"guid": "toast-order-3", "checks": [{"customer": {}, "selections": []}]},
]


class TestToastIntegration:
    def _make_toast_biz(self):
        return _make_business(
            pos_type="toast",
            token="",
            merchant_id="REST-GUID-123",
            toast_client_id="client-id",
            toast_client_secret="client-secret",
        )

    def test_returns_normalised_orders(self):
        biz = self._make_toast_biz()
        auth_resp = MagicMock()
        auth_resp.status_code = 200
        auth_resp.json.return_value = {"token": {"accessToken": "tok-abc"}}
        orders_resp = MagicMock()
        orders_resp.status_code = 200
        orders_resp.json.return_value = TOAST_RESPONSE

        with patch("requests.post", side_effect=[auth_resp, orders_resp]):
            with patch("requests.get", return_value=orders_resp):
                orders = ToastIntegration.get_orders(biz)

        assert len(orders) == 2
        assert orders[0]["customer_name"] == "Ahmed Al Rashid"
        assert "Pistachio Latte" in orders[0]["items"]
        assert orders[1]["customer_name"] == "Sara"

    def test_returns_empty_on_auth_failure(self):
        biz = self._make_toast_biz()
        auth_resp = MagicMock()
        auth_resp.status_code = 401

        with patch("requests.post", return_value=auth_resp):
            orders = ToastIntegration.get_orders(biz)

        assert orders == []

    def test_returns_empty_on_orders_api_error(self):
        biz = self._make_toast_biz()
        auth_resp = MagicMock()
        auth_resp.status_code = 200
        auth_resp.json.return_value = {"token": {"accessToken": "tok-abc"}}
        orders_resp = MagicMock()
        orders_resp.status_code = 403
        orders_resp.json.return_value = []

        with patch("requests.post", return_value=auth_resp):
            with patch("requests.get", return_value=orders_resp):
                orders = ToastIntegration.get_orders(biz)

        assert orders == []


# ---------------------------------------------------------------------------
# LightspeedIntegration
# ---------------------------------------------------------------------------

LIGHTSPEED_RESPONSE = {
    "Sale": [
        {
            "saleID": "LS-001",
            "name": "Ahmed",
            "timeStamp": "2024-01-01T12:00:00+00:00",
            "SaleLines": {
                "SaleLine": [
                    {"Item": {"description": "Flat White"}},
                    {"Item": {"description": "Croissant"}},
                ]
            },
        },
        {
            "saleID": "LS-002",
            "name": "Sara",
            "timeStamp": "2024-01-01T12:05:00+00:00",
            "SaleLines": {"SaleLine": [{"Item": {"description": "Green Tea"}}]},
        },
        # No name — should be excluded
        {"saleID": "LS-003", "name": "", "timeStamp": "2024-01-01T12:10:00+00:00", "SaleLines": {}},
    ]
}


class TestLightspeedIntegration:
    def _make_ls_biz(self):
        return _make_business(pos_type="lightspeed", token="ls-api-key", merchant_id="987654")

    def test_returns_normalised_orders(self):
        biz = self._make_ls_biz()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = LIGHTSPEED_RESPONSE

        with patch("requests.get", return_value=mock_resp):
            orders = LightspeedIntegration.get_orders(biz)

        assert len(orders) == 2
        assert orders[0]["id"] == "LS-001"
        assert orders[0]["customer_name"] == "Ahmed"
        assert "Flat White" in orders[0]["items"]
        assert orders[1]["customer_name"] == "Sara"

    def test_single_sale_line_as_dict(self):
        """When the API returns a single SaleLine as a dict instead of a list."""
        biz = self._make_ls_biz()
        data = {
            "Sale": [{
                "saleID": "LS-010",
                "name": "Bob",
                "timeStamp": "2024-01-01T12:00:00+00:00",
                "SaleLines": {"SaleLine": {"Item": {"description": "Espresso"}}},
            }]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = data

        with patch("requests.get", return_value=mock_resp):
            orders = LightspeedIntegration.get_orders(biz)

        assert len(orders) == 1
        assert "Espresso" in orders[0]["items"]

    def test_returns_empty_on_api_error(self):
        biz = self._make_ls_biz()
        mock_resp = MagicMock()
        mock_resp.status_code = 401

        with patch("requests.get", return_value=mock_resp):
            orders = LightspeedIntegration.get_orders(biz)

        assert orders == []


# ---------------------------------------------------------------------------
# Analytics fields: order_total and order_reference
# ---------------------------------------------------------------------------

class TestPOSAnalyticsFields:
    """Verify order_total (cents) and order_reference are returned by each integration."""

    def test_clover_order_total_in_cents(self):
        biz = _make_business("clover")
        response = {
            "elements": [{
                "id": "c1",
                "note": "Alice",
                "createdTime": 1700000000000,
                "total": 1250,  # $12.50
                "lineItems": {"elements": [{"name": "Latte"}]},
            }]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = response
        with patch("requests.get", return_value=mock_resp):
            orders = CloverIntegration.get_orders(biz)
        assert orders[0]["order_total"] == 1250
        assert orders[0]["order_reference"] == ""

    def test_square_order_total_and_reference(self):
        biz = _make_business("square")
        response = {
            "orders": [{
                "id": "sq1",
                "ticket_name": "Bob",
                "created_at": "2024-01-01T12:00:00Z",
                "line_items": [{"name": "Coffee"}],
                "total_money": {"amount": 450, "currency": "CAD"},
                "reference_id": "REF-99",
            }]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = response
        with patch("requests.post", return_value=mock_resp):
            orders = SquareIntegration.get_orders(biz)
        assert orders[0]["order_total"] == 450
        # ticket_name takes priority over reference_id
        assert orders[0]["order_reference"] == "Bob"

    def test_toast_order_total_converted_to_cents(self):
        """Toast returns totalAmount as dollars (float) — we convert to cents."""
        biz = _make_business("toast", toast_client_id="cid", toast_client_secret="sec")
        orders_data = [{
            "guid": "t1",
            "createdDate": "2024-01-01T12:00:00Z",
            "displayNumber": "T-42",
            "checks": [{
                "customer": {"firstName": "Carol", "lastName": ""},
                "totalAmount": 8.50,
                "selections": [{"displayName": "Espresso"}],
            }]
        }]
        auth_resp = MagicMock()
        auth_resp.status_code = 200
        auth_resp.json.return_value = {"token": {"accessToken": "tok"}}
        orders_resp = MagicMock()
        orders_resp.status_code = 200
        orders_resp.json.return_value = orders_data
        with patch("requests.post", return_value=auth_resp):
            with patch("requests.get", return_value=orders_resp):
                orders = ToastIntegration.get_orders(biz)
        assert orders[0]["order_total"] == 850  # $8.50 → 850 cents
        assert orders[0]["order_reference"] == "T-42"

    def test_lightspeed_order_total_and_reference(self):
        biz = _make_business("lightspeed")
        response = {
            "Sale": [{
                "saleID": "ls1",
                "name": "Dave",
                "timeStamp": "2024-01-01T12:00:00+00:00",
                "calcTotal": "15.75",
                "receiptNum": "R-007",
                "SaleLines": {"SaleLine": {"Item": {"description": "Tea"}}},
            }]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = response
        with patch("requests.get", return_value=mock_resp):
            orders = LightspeedIntegration.get_orders(biz)
        assert orders[0]["order_total"] == 1575  # $15.75 → 1575 cents
        assert orders[0]["order_reference"] == "R-007"

    def test_match_customer_includes_ordered_at_and_total(self):
        """match_customer result orders include ordered_at and order_total."""
        biz = _make_business("clover")
        fake_orders = [{
            "id": "c1",
            "customer_name": "Alice",
            "items": ["Latte"],
            "created_at": "2024-01-01T12:00:00Z",
            "order_total": 1250,
            "order_reference": "",
        }]
        with patch.object(POSIntegration, "get_recent_orders", return_value=fake_orders):
            result = POSIntegration.match_customer(biz, customer_name="Alice")
        assert result["matched"] is True
        assert result["orders"][0]["ordered_at"] == "2024-01-01T12:00:00Z"
        assert result["orders"][0]["order_total"] == 1250
