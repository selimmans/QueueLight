# KNOWN_ISSUES.md — Queue Light

Start empty. Add known bugs, edge cases, deferred decisions, and open questions here as they are discovered. Do not delete entries — mark them RESOLVED if fixed.

---

## Open Issues

**Late arrival notification not shown on staff dashboard** — when a customer taps "I'm still coming" on the confirmation page after being abandoned/skipped, a `LATE_ARRIVAL` event is logged to QueueEventLog but no banner appears on the staff dashboard. Staff won't know unless they check the admin panel.
STATUS: OPEN — deferred.

**QR cache is process-local** — Django's default in-memory cache means each gunicorn worker generates the QR PNG on its first request. Not a bug in single-worker dev; in production with multiple workers, use a shared cache backend (Redis or memcached).
STATUS: OPEN — acceptable for single-worker deploys (Railway default).

**Intake answers not preserved on join form validation error** — if the customer submits the join form with an error (e.g. invalid phone), the intake answer inputs are cleared. The name field is preserved but intake fields are not.
STATUS: OPEN — low priority, rare edge case.

---

## Deferred Decisions

**App name `queues` (not `queue`)** — Python's stdlib has a `queue` module. Naming the Django app `queue` causes an import conflict. App is named `queues` throughout.
STATUS: RESOLVED — decision made at scaffold time.

**Batch show-up count assigns completed/abandoned by position order** — when staff tap a count N, the first N called entries (by position) are marked completed; the rest are abandoned. The specific assignment is arbitrary since batch mode doesn't track individuals. Aggregate count is accurate in event log.
STATUS: RESOLVED — intentional, documented here for context.

**Individual customer tracking in batch mode not implemented** — show-up count is aggregate only. Per-customer attendance history, loyalty signals, and no-show rates per individual are not tracked. Individual-level resolution would require staff to identify each person by name at completion time — deferred until there's a real user need.
STATUS: OPEN — deferred by design.

**business_type = clinic does not yet unlock extra features** — the field exists and hides menu_url in the settings UI, but the staff dashboard and confirmation page are identical for retail and clinic. Clinic-specific features (appointment context, intake review panel, etc.) are the next step for that track.
STATUS: OPEN — intentional, field is in place for when the time comes.

---

**Pickup entries have no expiry / auto-archival** — PickupEntry rows with status=waiting or status=ready accumulate indefinitely. Staff must mark each as Picked Up manually or entries stay on the dashboard forever. No background job exists to age out stale entries.
STATUS: OPEN — deferred. Low impact in early deployments. Consider a daily management command to auto-abandon old entries.

**Pickup polling is independent of queue polling** — when both features are enabled, the dashboard makes two separate fetch() calls every 5 seconds (one for queue, one for pickup). This is intentional for simplicity but doubles polling load.
STATUS: OPEN — acceptable. Could be merged into one combined endpoint later.

---

**POS API token stored plaintext** — `Business.pos_api_token` is a CharField with no at-rest encryption. Consistent with how `twilio_from_number` and other config is stored. Acceptable for early deployments. Proper encryption (e.g. django-fernet-fields) deferred until multi-tenant security requirements are clearer.
STATUS: OPEN — deferred by design.

**POS name matching is first-name-only unreliable** — `token_sort_ratio` with threshold 0.75 reliably matches full names and transposed names, but a customer entering only a first name (e.g. "Mohamed") against a POS order with a full name ("Mohamed Al Rashid") may fall below threshold (~0.61) and land in manual fallback. Staff can ask the customer to enter their full name or use the fallback flow. Raising the threshold to 0.65 would help but risks false positives.
STATUS: OPEN — known trade-off in fuzzy matching.

**POS order match re-fetches on form submit not implemented** — when a customer confirms a POS match ("Yes, that's me"), the `pos_order_items` sent in the hidden form field are trusted from the client. This is display-only data (staff see item names), not security-sensitive. A server-side re-verification on submit was considered but adds latency.
STATUS: OPEN — intentional for v1.

**Join page field config not enforced in POS flow phone step** — `field_phone_required` is enforced in the POS-confirmed path but the POS flow's phone step UI does not show the "required" attribute on the phone input when `field_phone_required=True`. The server-side validation does block submission, but the browser won't highlight the field before submission.
STATUS: OPEN — low priority. Server-side guard is correct; UI polish deferred.

---

## Resolved Issues

**Test cache bleed between transactions** — `PickupJoinView._get_business()` cached Business objects in-memory for 30 s. In pytest, rolled-back transactions left stale cached objects with dangling pks, causing intermittent test failures. RESOLVED by adding `clear_django_cache` autouse fixture in `conftest.py`.
STATUS: RESOLVED.
