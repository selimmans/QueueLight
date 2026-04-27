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

## Resolved Issues

_(none yet)_
