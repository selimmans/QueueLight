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
# Phone extraction helper
# ---------------------------------------------------------------------------

import re

# Matches common North American and international phone patterns typed anywhere
# in a text field — with or without country code, spaces, dashes, dots, parens.
_PHONE_PATTERN = re.compile(
    r"(?<!\d)"                          # not preceded by a digit
    r"(\+?1[\s.\-]?)?"                  # optional +1 or 1 country code
    r"\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}"
    r"(?!\d)"                           # not followed by a digit
)


def _extract_phone(text: str, country: str = "CA") -> str:
    """Scan *text* for anything that looks like a phone number.

    Returns an E.164 string (e.g. '+16135550001') or '' if nothing found.
    Uses the phonenumbers library for normalisation so regional formats work.
    """
    if not text:
        return ""
    try:
        import phonenumbers as _pn
        for m in _PHONE_PATTERN.finditer(text):
            raw = m.group(0).strip()
            try:
                parsed = _pn.parse(raw, country)
                if _pn.is_valid_number(parsed):
                    return _pn.format_number(parsed, _pn.PhoneNumberFormat.E164)
            except Exception:
                continue
    except Exception:
        pass
    return ""


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
                            # Clover total is already in cents (int)
                            "order_total": order.get("total"),
                            # Clover has no separate receipt number in the standard API
                            "order_reference": "",
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
    def get_customer_phone(business, customer_id: str) -> str:
        """Fetch a customer's phone number from Square, with 10-min cache.

        Returns E.164 string or "" if unavailable.
        """
        from django.core.cache import cache
        import requests as _req

        cache_key = f"sq_cust_phone:{customer_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            resp = _req.get(
                f"{SquareIntegration.BASE_URL}/customers/{customer_id}",
                headers={"Authorization": f"Bearer {business.pos_api_token}"},
                timeout=5,
            )
            if resp.status_code == 200:
                phone = (
                    resp.json().get("customer", {}).get("phone_number") or ""
                ).strip()
                cache.set(cache_key, phone, timeout=600)
                return phone
        except Exception:
            logger.exception("Square customer lookup failed for %s", customer_id)

        cache.set(cache_key, "", timeout=60)  # cache miss briefly
        return ""

    @staticmethod
    def get_orders(business, minutes: int = 120) -> list[dict]:
        """Return recent Square orders as normalised dicts.

        Uses merchant's access token from the Square Developer dashboard.
        pos_merchant_id is used as the Square location_id.
        Includes customer phone when a customer_id is linked to the order.
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

            raw_orders = resp.json().get("orders", [])
            logger.info("Square returned %d raw orders for %s", len(raw_orders), business.slug)
            orders = []
            for order in raw_orders:
                # Ticket number is what staff see and call out
                ticket_name = order.get("ticket_name", "").strip()
                order_reference = ticket_name or order.get("reference_id", "").strip() or order.get("id", "")[:6]

                items = [
                    li["name"]
                    for li in order.get("line_items", [])
                    if li.get("name")
                ]

                # Phone: check Customer API via order.customer_id and tender customer_ids
                phone = ""
                customer_ids = set()
                if order.get("customer_id"):
                    customer_ids.add(order["customer_id"])
                for tender in order.get("tenders", []):
                    if tender.get("customer_id"):
                        customer_ids.add(tender["customer_id"])
                for cid in customer_ids:
                    phone = SquareIntegration.get_customer_phone(business, cid)
                    if phone:
                        break

                total_money = order.get("total_money") or {}
                orders.append({
                    "id": order["id"],
                    "customer_name": "",
                    "items": items,
                    "created_at": order.get("created_at"),
                    "order_total": total_money.get("amount"),
                    "order_reference": order_reference,
                    "phone": phone,
                })
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
                # Toast totalAmount is in dollars (float) — convert to cents
                total_amount = check.get("totalAmount")
                try:
                    order_total = round(float(total_amount) * 100) if total_amount is not None else None
                except (TypeError, ValueError):
                    order_total = None
                orders.append(
                    {
                        "id": order.get("guid", ""),
                        "customer_name": customer_name,
                        "items": items,
                        "created_at": order.get("createdDate"),
                        "order_total": order_total,
                        # displayNumber is the human-readable ticket number
                        "order_reference": str(order.get("displayNumber") or order.get("externalId") or ""),
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
                # Lightspeed calcTotal is a decimal string like "12.50"
                try:
                    order_total = round(float(sale.get("calcTotal", 0)) * 100)
                except (TypeError, ValueError):
                    order_total = None
                orders.append(
                    {
                        "id": str(sale.get("saleID", "")),
                        "customer_name": customer_name,
                        "items": items,
                        "created_at": sale.get("timeStamp"),
                        "order_total": order_total,
                        "order_reference": str(sale.get("receiptNum") or ""),
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

def _demo_pos_orders() -> list[dict]:
    """Hardcoded realistic café orders for the 'demo' POS type."""
    from datetime import datetime, timedelta, timezone as _tz
    now = datetime.now(_tz.utc)
    return [
        {
            "id": "DEMO-001",
            "customer_name": "Sarah Johnson",
            "items": ["Oat Milk Latte", "Blueberry Scone"],
            "created_at": (now - timedelta(minutes=14)).isoformat(),
            "order_total": 1275,
            "order_reference": "T-41",
        },
        {
            "id": "DEMO-002",
            "customer_name": "Ahmed Al-Rashid",
            "items": ["Double Americano", "Avocado Toast"],
            "created_at": (now - timedelta(minutes=9)).isoformat(),
            "order_total": 1850,
            "order_reference": "T-42",
        },
        {
            "id": "DEMO-003",
            "customer_name": "Emma Chen",
            "items": ["Matcha Latte", "Chocolate Croissant"],
            "created_at": (now - timedelta(minutes=3)).isoformat(),
            "order_total": 1150,
            "order_reference": "T-43",
        },
    ]


class POSIntegration:

    @staticmethod
    def get_recent_orders(business, minutes: int = 120) -> list[dict]:
        """Fetch orders from the connected POS. Returns [] if none configured."""
        if business.pos_type == "demo":
            return _demo_pos_orders()
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
                        "ordered_at": o.get("created_at"),
                        "order_total": o.get("order_total"),
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
                        "ordered_at": o.get("created_at"),
                        "order_total": o.get("order_total"),
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
                "ordered_at": o.get("created_at"),
                "order_total": o.get("order_total"),
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
