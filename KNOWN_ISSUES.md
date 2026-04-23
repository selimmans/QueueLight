# KNOWN_ISSUES.md — Queue Light

Start empty. Add known bugs, edge cases, deferred decisions, and open questions here as they are discovered. Do not delete entries — mark them RESOLVED if fixed.

---

## Open Issues

_(none yet)_

## Deferred Decisions

**App name `queues` (not `queue`)** — Python's stdlib has a `queue` module. Naming the Django app `queue` causes an import conflict (`AttributeError: module 'queue' has no attribute 'SimpleQueue'`) because the app directory's `__init__.py` shadows the stdlib. App is named `queues` throughout. The URL namespace and model verbose names still say "queue" where appropriate.
STATUS: RESOLVED — decision made at scaffold time.

---

## Deferred Decisions

_(none yet)_

---

## Resolved Issues

_(none yet)_
