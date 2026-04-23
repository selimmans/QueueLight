# ARCHITECTURE.md — Queue Light

Keep this document current. Update it whenever models, URLs, or core logic changes.

---

## System Overview

Queue Light is a minimal virtual queue system for Canadian retail and service businesses.

- Backend: Django 5 + Django REST Framework (for internal JSON API used by the dashboard poll)
- Database: PostgreSQL
- SMS: Twilio (synchronous, called at call_next() time)
- No WebSockets. No Celery. No Redis.
- Staff dashboard polls the queue every 5 seconds via `fetch()`.
- Customers use a normal mobile-optimised webpage — no PWA, no service worker.

---

## App Structure

```
queuelight/
├── config/          Django project config (settings, URLs, wsgi)
├── businesses/      Business model, StaffPhone model
├── queues/          QueueEntry, QueueEventLog, QueueService
├── notifications/   TwilioSMSBackend
├── customer/        /q/<slug>/ join + confirmation views
├── dashboard/       /staff/<slug>/ queue dashboard + auth views
└── core/            Scoping helpers, health check
```

---

## Models

### businesses.Business

| Field             | Type         | Notes                                     |
|-------------------|--------------|-------------------------------------------|
| id                | BigAutoField | PK                                        |
| name              | CharField    | Display name                              |
| slug              | SlugField    | URL-safe identifier, unique               |
| logo_colour       | CharField    | Hex colour string e.g. "#3B82F6"          |
| mode              | CharField    | "batch" or "person"                       |
| batch_size        | PositiveIntegerField | Only used in batch mode. Default 5. |
| twilio_from_number| CharField    | Twilio sender number for this business    |
| is_active         | BooleanField | Inactive businesses reject new joins      |
| created_at        | DateTimeField| auto_now_add                              |

### businesses.StaffPhone

| Field    | Type         | Notes                                |
|----------|--------------|--------------------------------------|
| id       | BigAutoField | PK                                   |
| phone    | CharField    | E.164 format, unique per business    |
| business | FK → Business| CASCADE                              |
| name     | CharField    | Display name for the staff member    |

Constraint: unique_together (phone, business)

Staff auth flow: staff enters phone number → system looks up StaffPhone → if found, creates session with business_id and staff_phone_id → redirect to /staff/<slug>/. No password. No Django User model required for staff.

### queue.QueueEntry

| Field       | Type          | Notes                                              |
|-------------|---------------|----------------------------------------------------|
| id          | BigAutoField  | PK                                                 |
| business    | FK → Business | CASCADE                                            |
| name        | CharField     | Customer name                                      |
| phone       | CharField     | Customer phone (E.164)                             |
| status      | CharField     | WAITING / CALLED / COMPLETED / ABANDONED / SKIPPED |
| position    | PositiveIntegerField | Sequential position within the current queue session |
| batch_number| PositiveIntegerField | Null in person mode. Batch number in batch mode.  |
| joined_at   | DateTimeField | auto_now_add                                       |
| called_at   | DateTimeField | Null until called                                  |

### queue.QueueEventLog

Immutable. Never update rows. Only insert.

| Field        | Type          | Notes                                                |
|--------------|---------------|------------------------------------------------------|
| id           | BigAutoField  | PK                                                   |
| business     | FK → Business | CASCADE                                              |
| entry        | FK → QueueEntry | SET_NULL, nullable (for business-level events)     |
| event_type   | CharField     | JOINED / CALLED / SKIPPED / ABANDONED / SMS_SENT / SMS_FAILED |
| before_values| JSONField     | State before the event. {} for JOINED.               |
| after_values | JSONField     | State after the event.                               |
| timestamp    | DateTimeField | auto_now_add                                         |
| meta         | JSONField     | Extra context: mode, batch_size, batch_number        |

---

## State Machine

```
WAITING → CALLED → COMPLETED
WAITING → ABANDONED
WAITING → SKIPPED   (person mode only)
```

ALLOWED_TRANSITIONS (in queues/services.py):
```python
{
    "waiting":   {"called", "abandoned", "skipped"},
    "called":    {"completed"},
    "completed": set(),
    "abandoned": set(),
    "skipped":   set(),
}
```

Terminal states: COMPLETED, ABANDONED, SKIPPED

### QueueService.call_next()

1. Lock: `select_for_update()` on all WAITING entries for the business
2. Find next target:
   - Batch mode: find the lowest uncalled batch_number with any WAITING entry
   - Person mode: find the WAITING entry with the lowest position
3. Mark all matched entries as CALLED, set called_at = now()
4. Fire Twilio SMS to each called customer (synchronous)
5. Log QueueEventLog: CALLED event, one per entry
6. If SMS fails: log SMS_FAILED event, do not raise — call_next() still succeeds
7. All steps inside transaction.atomic()

---

## URL Map

| URL                          | View                        | Auth        | Notes                    |
|------------------------------|-----------------------------|-------------|--------------------------|
| GET /q/<slug>/               | customer.views.JoinView     | None        | Show join form           |
| POST /q/<slug>/              | customer.views.JoinView     | None        | Process join → redirect  |
| GET /q/<slug>/confirmation/  | customer.views.ConfirmView  | None        | Show batch/position number |
| GET /staff/<slug>/           | dashboard.views.DashboardView | Session   | Queue list               |
| POST /staff/<slug>/next/     | dashboard.views.CallNextView | Session    | Trigger call_next()      |
| GET /staff/<slug>/qr.png     | dashboard.views.QRView      | Session     | QR code PNG              |
| GET /staff/<slug>/login/     | dashboard.views.StaffLoginView | None     | Phone entry form         |
| POST /staff/<slug>/login/    | dashboard.views.StaffLoginView | None     | Authenticate staff       |
| GET /staff/<slug>/logout/    | dashboard.views.StaffLogoutView | Session  | Clear session            |
| GET /health/                 | core.views.HealthCheckView  | None        | DB health probe          |
| GET /admin/                  | Django admin                | is_staff    | Platform admin           |
| GET /api/queue/<slug>/status/| dashboard.views.QueueStatusAPIView | Session | Polling endpoint — returns JSON queue state |

---

## SMS Flow

1. `QueueService.call_next()` calls `notifications.sms.TwilioSMSBackend.send()`
2. `TwilioSMSBackend` sends via Twilio REST API (synchronous HTTP call)
3. On success: logs SMS_SENT to QueueEventLog
4. On failure: logs SMS_FAILED to QueueEventLog, swallows exception, returns False
5. call_next() completes regardless of SMS outcome

---

## Polling

Staff dashboard polls `/api/queue/<slug>/status/` every 5 seconds using `setInterval` + `fetch()`.
Response: `{ waiting: [...], called_last: {...}, mode, batch_size }`.
No WebSockets. No Channels. No Redis.

---

## Business Scoping

Every queryset involving QueueEntry or QueueEventLog is filtered by `business_id`.
Business is looked up from the URL slug. Cross-business access returns 404.
Staff session stores `business_id` — all dashboard queries are implicitly scoped.

---

## Data Collection

QueueEventLog stores every state transition silently. Not shown in any UI yet.
Every row includes `meta.mode` and `meta.batch_size` for future analytics.
