"""Read-only POS integrations for pickup order matching.

Supports Clover and Square. We only ever READ from the POS — we never
write, never process payments, and never store raw POS responses beyond
the matched order id and item names.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Clover
# ---------------------------------------------------------------------------

class CloverIntegration:
    BASE_URL = "https://api.clover.com/v3"

    @staticmethod
    def get_orders(business, minutes: int = 120) -> list[dict]:
        """Return recent Clover orders as normalised dicts.

        Uses the merchant's API token (generated in Clover dashboard under
        Account & Setup → API Tokens).  No App Market approval required for
        read-only access with a merchant token.
        """
        import requests as _req

        since_ms = int(
            (datetime.now(timezone.utc) - timedelta(minutes=minutes)).timestamp() * 1000
        )
        url = (
            f"{CloverIntegration.BASE_URL}/merchants/"
            f"{business.pos_merchant_id}/orders"
        )
        params = {
            "filter": f"createdTime>={since_ms}",
            "expand": "lineItems",
            "limit": 100,
        }
        headers = {"Authorization": f"Bearer {business.pos_api_token}"}

        try:
            resp = _req.get(url, headers=headers, params=params, timeout=5)
            if resp.status_code != 200:
                logger.warning(
                    "Clover API error %s for %s", resp.status_code, business.slug
                )
                return []

            orders = []
            for order in resp.json().get("elements", []):
                customer_name = (order.get("note") or order.get("title") or "").strip()
                items = [
                    item["name"]
                    for item in order.get("lineItems", {}).get("elements", [])
                    if item.get("name")
                ]
                if customer_name:
                    orders.append(
                        {
                            "id": order["id"],
                            "customer_name": customer_name,
                            "items": items,
                            "created_at": order.get("createdTime"),
                        }
                    )
            return orders

        except Exception:
            logger.exception("Clover fetch failed for %s", business.slug)
            return []

    @staticmethod
    def test_connection(business) -> dict:
        """Return {ok, message} for the Settings 'Test connection' button."""
        orders = CloverIntegration.get_orders(business, minutes=120)
        if orders is None:
            return {"ok": False, "message": "Connection failed — check your token and merchant ID."}
        return {
            "ok": True,
            "message": f"Connected — {len(orders)} order(s) found in the last 2 hours.",
        }


# ---------------------------------------------------------------------------
# Square
# ---------------------------------------------------------------------------

class SquareIntegration:
    BASE_URL = "https://connect.squareup.com/v2"

    @staticmethod
    def get_orders(business, minutes: int = 120) -> list[dict]:
        """Return recent Square orders as normalised dicts.

        Uses merchant's access token from the Square Developer dashboard.
        pos_merchant_id is used as the Square location_id.
        """
        import requests as _req

        since = (
            datetime.now(timezone.utc) - timedelta(minutes=minutes)
        ).isoformat()

        url = f"{SquareIntegration.BASE_URL}/orders/search"
        headers = {
            "Authorization": f"Bearer {business.pos_api_token}",
            "Content-Type": "application/json",
        }
        body = {
            "location_ids": [business.pos_merchant_id],
            "query": {
                "filter": {
                    "date_time_filter": {"created_at": {"start_at": since}},
                    "state_filter": {"states": ["OPEN", "COMPLETED"]},
                }
            },
            "limit": 100,
        }

        try:
            resp = _req.post(url, headers=headers, json=body, timeout=5)
            if resp.status_code != 200:
                logger.warning(
                    "Square API error %s for %s", resp.status_code, business.slug
                )
                return []

            orders = []
            for order in resp.json().get("orders", []):
                # Try ticket_name first, then pickup fulfillment recipient
                customer_name = order.get("ticket_name", "").strip()
                if not customer_name:
                    for f in order.get("fulfillments", []):
                        recipient = f.get("pickup_details", {}).get("recipient", {})
                        customer_name = recipient.get("display_name", "").strip()
                        if customer_name:
                            break

                items = [
                    li["name"]
                    for li in order.get("line_items", [])
                    if li.get("name")
                ]
                if customer_name:
                    orders.append(
                        {
                            "id": order["id"],
                            "customer_name": customer_name,
                            "items": items,
                            "created_at": order.get("created_at"),
                        }
                    )
            return orders

        except Exception:
            logger.exception("Square fetch failed for %s", business.slug)
            return []

    @staticmethod
    def test_connection(business) -> dict:
        orders = SquareIntegration.get_orders(business, minutes=120)
        if orders is None:
            return {"ok": False, "message": "Connection failed — check your token and location ID."}
        return {
            "ok": True,
            "message": f"Connected — {len(orders)} order(s) found in the last 2 hours.",
        }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

class POSIntegration:

    @staticmethod
    def get_recent_orders(business, minutes: int = 120) -> list[dict]:
        """Fetch orders from the connected POS. Returns [] if none configured."""
        if business.pos_type == business.POS_CLOVER:
            return CloverIntegration.get_orders(business, minutes)
        if business.pos_type == business.POS_SQUARE:
            return SquareIntegration.get_orders(business, minutes)
        return []

    @staticmethod
    def match_customer(business, customer_name: str) -> dict:
        """Fuzzy-match *customer_name* against recent POS orders.

        Returns::

            {
                "matched": bool,
                "order_id": str | None,
                "order_items": list[str],
                "confidence": float,   # 0–1
            }
        """
        from rapidfuzz import fuzz

        _no_match = {
            "matched": False,
            "order_id": None,
            "order_items": [],
            "confidence": 0.0,
        }

        if not customer_name or not customer_name.strip():
            return _no_match

        orders = POSIntegration.get_recent_orders(business)
        if not orders:
            return _no_match

        needle = customer_name.lower().strip()
        best_order, best_score = None, 0.0

        for order in orders:
            haystack = order["customer_name"].lower().strip()
            # Use token_sort_ratio so "Ahmed Al" matches "Al Ahmed"
            score = fuzz.token_sort_ratio(needle, haystack) / 100.0
            if score > best_score:
                best_score = score
                best_order = order

        THRESHOLD = 0.75
        if best_score >= THRESHOLD and best_order:
            return {
                "matched": True,
                "order_id": best_order["id"],
                "order_items": best_order["items"],
                "confidence": round(best_score, 4),
            }

        return {**_no_match, "confidence": round(best_score, 4)}

    @staticmethod
    def test_connection(business) -> dict:
        """Called from Settings 'Test connection' button."""
        if business.pos_type == business.POS_CLOVER:
            return CloverIntegration.test_connection(business)
        if business.pos_type == business.POS_SQUARE:
            return SquareIntegration.test_connection(business)
        return {"ok": False, "message": "No POS type selected."}
