"""Read-only POS integrations for pickup order matching.

Supports Clover, Square, Toast, and Lightspeed. We only ever READ from
the POS — we never write, never process payments, and never store raw
POS responses beyond the matched order id and item names.
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
# Toast
# ---------------------------------------------------------------------------

# Toast OAuth2 token cache: {cache_key: (token, expires_at)}
_toast_token_cache: dict[str, tuple[str, datetime]] = {}


class ToastIntegration:
    AUTH_URL = "https://ws-api.toasttab.com/authentication/v1/authentication/login"
    ORDERS_URL = "https://ws-api.toasttab.com/orders/v2/ordersBulk"
    # Token lifetime minus 5-min safety margin → 50 min
    TOKEN_TTL_SECONDS = 50 * 60

    @staticmethod
    def _get_token(business) -> str | None:
        """Return a valid OAuth2 bearer token, using a 50-min in-process cache."""
        import requests as _req

        cache_key = f"toast:{business.pos_merchant_id}:{business.toast_client_id}"
        cached = _toast_token_cache.get(cache_key)
        if cached:
            token, expires_at = cached
            if datetime.now(timezone.utc) < expires_at:
                return token

        try:
            resp = _req.post(
                ToastIntegration.AUTH_URL,
                json={
                    "clientId": business.toast_client_id,
                    "clientSecret": business.toast_client_secret,
                    "userAccessType": "TOAST_MACHINE_CLIENT",
                },
                timeout=5,
            )
            if resp.status_code != 200:
                logger.warning(
                    "Toast auth error %s for %s", resp.status_code, business.slug
                )
                return None

            data = resp.json()
            token = data.get("token", {}).get("accessToken") or data.get("accessToken")
            if not token:
                logger.warning("Toast auth: no accessToken in response for %s", business.slug)
                return None

            expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=ToastIntegration.TOKEN_TTL_SECONDS
            )
            _toast_token_cache[cache_key] = (token, expires_at)
            return token

        except Exception:
            logger.exception("Toast auth failed for %s", business.slug)
            return None

    @staticmethod
    def get_orders(business, minutes: int = 120) -> list[dict]:
        """Return recent Toast orders as normalised dicts."""
        import requests as _req

        token = ToastIntegration._get_token(business)
        if not token:
            return []

        since = (
            datetime.now(timezone.utc) - timedelta(minutes=minutes)
        ).strftime("%Y%m%d%H%M%S")

        headers = {
            "Authorization": f"Bearer {token}",
            "Toast-Restaurant-External-ID": business.pos_merchant_id,
        }

        try:
            resp = _req.get(
                ToastIntegration.ORDERS_URL,
                headers=headers,
                params={"startDate": since, "pageSize": 100},
                timeout=5,
            )
            if resp.status_code != 200:
                logger.warning(
                    "Toast orders API error %s for %s", resp.status_code, business.slug
                )
                return []

            orders = []
            for order in resp.json() if isinstance(resp.json(), list) else []:
                checks = order.get("checks", [])
                if not checks:
                    continue
                check = checks[0]
                customer = check.get("customer", {}) or {}
                first = (customer.get("firstName") or "").strip()
                last = (customer.get("lastName") or "").strip()
                customer_name = f"{first} {last}".strip() if (first or last) else ""
                if not customer_name:
                    customer_name = (order.get("externalId") or "").strip()
                if not customer_name:
                    continue
                items = [
                    sel["displayName"]
                    for sel in check.get("selections", [])
                    if sel.get("displayName")
                ]
                orders.append(
                    {
                        "id": order.get("guid", ""),
                        "customer_name": customer_name,
                        "items": items,
                        "created_at": order.get("createdDate"),
                    }
                )
            return orders

        except Exception:
            logger.exception("Toast fetch failed for %s", business.slug)
            return []

    @staticmethod
    def test_connection(business) -> dict:
        token = ToastIntegration._get_token(business)
        if not token:
            return {
                "ok": False,
                "message": "Authentication failed — check your Client ID, Client Secret, and Restaurant GUID.",
            }
        orders = ToastIntegration.get_orders(business, minutes=120)
        return {
            "ok": True,
            "message": f"Connected — {len(orders)} order(s) found in the last 2 hours.",
        }


# ---------------------------------------------------------------------------
# Lightspeed
# ---------------------------------------------------------------------------

class LightspeedIntegration:
    BASE_URL = "https://api.lightspeedapp.com/API/V3/Account"

    @staticmethod
    def get_orders(business, minutes: int = 120) -> list[dict]:
        """Return recent Lightspeed sales as normalised dicts.

        pos_api_token = Lightspeed API key.
        pos_merchant_id = Lightspeed account ID.
        """
        import requests as _req

        since = (
            datetime.now(timezone.utc) - timedelta(minutes=minutes)
        ).strftime("%Y-%m-%dT%H:%M:%S+00:00")

        url = (
            f"{LightspeedIntegration.BASE_URL}/"
            f"{business.pos_merchant_id}/Sale.json"
        )
        headers = {"Authorization": f"Bearer {business.pos_api_token}"}
        params = {
            "limit": 100,
            "sort": "timeStamp,DESC",
            "timeStamp": f">,{since}",
        }

        try:
            resp = _req.get(url, headers=headers, params=params, timeout=5)
            if resp.status_code != 200:
                logger.warning(
                    "Lightspeed API error %s for %s", resp.status_code, business.slug
                )
                return []

            data = resp.json()
            raw_sales = data.get("Sale", [])
            if isinstance(raw_sales, dict):
                raw_sales = [raw_sales]

            orders = []
            for sale in raw_sales:
                customer_name = (sale.get("name") or "").strip()
                if not customer_name:
                    continue

                # SaleLines may be a dict (single item) or a list
                sale_lines_wrapper = sale.get("SaleLines", {})
                if isinstance(sale_lines_wrapper, dict):
                    raw_lines = sale_lines_wrapper.get("SaleLine", [])
                    if isinstance(raw_lines, dict):
                        raw_lines = [raw_lines]
                else:
                    raw_lines = []

                items = [
                    line.get("Item", {}).get("description", "")
                    for line in raw_lines
                    if line.get("Item", {}).get("description")
                ]
                orders.append(
                    {
                        "id": str(sale.get("saleID", "")),
                        "customer_name": customer_name,
                        "items": items,
                        "created_at": sale.get("timeStamp"),
                    }
                )
            return orders

        except Exception:
            logger.exception("Lightspeed fetch failed for %s", business.slug)
            return []

    @staticmethod
    def test_connection(business) -> dict:
        orders = LightspeedIntegration.get_orders(business, minutes=120)
        if orders is None:
            return {
                "ok": False,
                "message": "Connection failed — check your API key and account ID.",
            }
        return {
            "ok": True,
            "message": f"Connected — {len(orders)} sale(s) found in the last 2 hours.",
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
        if business.pos_type == business.POS_TOAST:
            return ToastIntegration.get_orders(business, minutes)
        if business.pos_type == business.POS_LIGHTSPEED:
            return LightspeedIntegration.get_orders(business, minutes)
        return []

    @staticmethod
    def match_customer(
        business,
        customer_name: str = "",
        phone: str = "",
        order_number: str = "",
    ) -> dict:
        """Match a customer against recent POS orders using three signals.

        Priority order:
          1. Phone — exact match on the order's customer phone (if POS provides it)
          2. Order number / order reference — exact match
          3. Name — fuzzy match via token_sort_ratio (threshold 0.75)

        Returns::

            {
                "matched": bool,
                "multiple": bool,           # True when >1 name-fuzzy matches found
                "orders": [                 # list of matched orders (usually 1)
                    {
                        "order_id": str,
                        "order_reference": str,
                        "items": list[str],
                        "confidence": float,
                    }
                ]
            }

        Legacy callers that only pass customer_name still work — the return dict
        also exposes "order_id", "order_items", and "confidence" at the top level
        (derived from the first/best match) for backward compatibility.
        """
        from rapidfuzz import fuzz

        _no_match: dict = {
            "matched": False,
            "multiple": False,
            "orders": [],
            # Legacy keys
            "order_id": None,
            "order_items": [],
            "confidence": 0.0,
        }

        orders = POSIntegration.get_recent_orders(business)
        if not orders:
            return _no_match

        # ── 1. Phone exact match ─────────────────────────────────────────
        if phone and phone.strip():
            phone_needle = phone.strip().replace(" ", "")
            phone_matches = [
                o for o in orders
                if o.get("phone", "").replace(" ", "") == phone_needle
            ]
            if phone_matches:
                matched_orders = [
                    {
                        "order_id": o["id"],
                        "order_reference": str(o.get("order_reference") or o["id"]),
                        "items": o["items"],
                        "confidence": 1.0,
                    }
                    for o in phone_matches
                ]
                first = matched_orders[0]
                return {
                    "matched": True,
                    "multiple": len(matched_orders) > 1,
                    "orders": matched_orders,
                    "order_id": first["order_id"],
                    "order_items": first["items"],
                    "confidence": 1.0,
                }

        # ── 2. Order number exact match ──────────────────────────────────
        if order_number and order_number.strip():
            ref_needle = order_number.strip().lstrip("#").lower()
            ref_matches = [
                o for o in orders
                if str(o.get("order_reference") or o["id"]).lstrip("#").lower() == ref_needle
            ]
            if ref_matches:
                matched_orders = [
                    {
                        "order_id": o["id"],
                        "order_reference": str(o.get("order_reference") or o["id"]),
                        "items": o["items"],
                        "confidence": 1.0,
                    }
                    for o in ref_matches
                ]
                first = matched_orders[0]
                return {
                    "matched": True,
                    "multiple": len(matched_orders) > 1,
                    "orders": matched_orders,
                    "order_id": first["order_id"],
                    "order_items": first["items"],
                    "confidence": 1.0,
                }

        # ── 3. Name fuzzy match ──────────────────────────────────────────
        if not customer_name or not customer_name.strip():
            return _no_match

        THRESHOLD = 0.75
        needle = customer_name.lower().strip()
        scored: list[tuple[float, dict]] = []

        for order in orders:
            haystack = order["customer_name"].lower().strip()
            score = fuzz.token_sort_ratio(needle, haystack) / 100.0
            if score >= THRESHOLD:
                scored.append((score, order))

        if not scored:
            # Return best-attempt confidence for diagnostics
            best_score = max(
                (fuzz.token_sort_ratio(needle, o["customer_name"].lower().strip()) / 100.0
                 for o in orders),
                default=0.0,
            )
            return {**_no_match, "confidence": round(best_score, 4)}

        scored.sort(key=lambda t: t[0], reverse=True)
        matched_orders = [
            {
                "order_id": o["id"],
                "order_reference": str(o.get("order_reference") or o["id"]),
                "items": o["items"],
                "confidence": round(score, 4),
            }
            for score, o in scored
        ]
        first = matched_orders[0]
        return {
            "matched": True,
            "multiple": len(matched_orders) > 1,
            "orders": matched_orders,
            "order_id": first["order_id"],
            "order_items": first["items"],
            "confidence": first["confidence"],
        }

    @staticmethod
    def test_connection(business) -> dict:
        """Called from Settings 'Test connection' button."""
        if business.pos_type == business.POS_CLOVER:
            return CloverIntegration.test_connection(business)
        if business.pos_type == business.POS_SQUARE:
            return SquareIntegration.test_connection(business)
        if business.pos_type == business.POS_TOAST:
            return ToastIntegration.test_connection(business)
        if business.pos_type == business.POS_LIGHTSPEED:
            return LightspeedIntegration.test_connection(business)
        return {"ok": False, "message": "No POS type selected."}
