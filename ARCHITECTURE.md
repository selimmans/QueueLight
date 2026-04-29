# ARCHITECTURE.md — Queue Light

Keep this document current. Update it whenever models, URLs, or core logic changes.

---

## System Overview

Queue Light is a virtual queue system for retail and clinic businesses.

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
└── core/            Health check
```

---

## Models

### businesses.Business

| Field              | Type                  | Notes                                                      |
|--------------------|-----------------------|------------------------------------------------------------|
| id                 | BigAutoField          | PK                                                         |
| name               | CharField             | Display name                                               |
| slug               | SlugField             | URL-safe identifier, unique                                |
| business_type      | CharField             | "retail" or "clinic". Controls which settings are visible. |
| logo_colour        | CharField             | Primary brand hex colour e.g. "#3B82F6"                   |
| colour_accent      | CharField             | Accent hex colour                                          |
| colour_border      | CharField             | Border hex colour                                          |
| mode               | CharField             | "batch" or "person"                                        |
| batch_size         | PositiveIntegerField  | Only used in batch mode. Default 5.                        |
| twilio_from_number | CharField             | Twilio sender number for this business                     |
| sms_template       | CharField             | SMS text with {business_name}/{customer_name} placeholders |
| menu_url           | URLField              | Shown as "View Menu" button on confirmation page (retail)  |
| intake_fields      | JSONField             | List of question strings asked at join time                |
| is_active          | BooleanField          | Inactive businesses reject new joins                       |
| is_closing         | BooleanField          | Join page shows closing msg, new POSTs blocked             |
| avg_service_minutes| PositiveIntegerField  | Used to estimate wait time range shown to customers        |
| country            | CharField             | ISO 3166-1 alpha-2. Used for phone validation + prefix.    |
| created_at         | DateTimeField         | auto_now_add                                               |

| queue_enabled      | BooleanField          | Default True. False hides queue form on join page.         |
| pickup_enabled     | BooleanField          | Default False. True shows pickup form on join page.        |
| pickup_notification_message | CharField  | SMS sent when order marked ready. Blank → default template.|

### businesses.StaffPhone

| Field    | Type         | Notes                                |
|----------|--------------|--------------------------------------|
| id       | BigAutoField | PK                                   |
| phone    | CharField    | E.164 format, unique per business    |
| business | FK → Business| CASCADE                              |
| name     | CharField    | Display name for the staff member    |

Constraint: unique_together (phone, business)

Staff auth flow: staff enters phone number → system looks up StaffPhone → if found, creates session with business_id and staff_phone_id → redirect to /staff/<slug>/. No password. No Django User required for staff. Platform superusers bypass this check entirely.

### queues.QueueEntry

| Field          | Type                  | Notes                                              |
|----------------|-----------------------|----------------------------------------------------|
| id             | BigAutoField          | PK                                                 |
| business       | FK → Business         | CASCADE                                            |
| name           | CharField             | Customer name                                      |
| phone          | CharField             | Customer phone (E.164)                             |
| status         | CharField             | WAITING / CALLED / COMPLETED / ABANDONED / SKIPPED |
| position       | PositiveIntegerField  | Sequential position within the current queue session |
| batch_number   | PositiveIntegerField  | Null in person mode. Batch number in batch mode.   |
| intake_answers | JSONField             | Dict of question → answer collected at join time   |
| joined_at      | DateTimeField         | auto_now_add                                       |
| called_at      | DateTimeField         | Null until called                                  |

### queues.QueueEventLog

Immutable. Never update rows. Only insert.

| Field        | Type          | Notes                                                |
|--------------|---------------|------------------------------------------------------|
| id           | BigAutoField  | PK                                                   |
| business     | FK → Business | CASCADE                                              |
| entry        | FK → QueueEntry | SET_NULL, nullable (for business-level events)     |
| event_type   | CharField     | JOINED / CALLED / COMPLETED / SKIPPED / ABANDONED / SMS_SENT / SMS_FAILED / LATE_ARRIVAL / LEFT / QUEUE_CLEARED / CLOSING_SOON_SMS |
| before_values| JSONField     | State before the event. {} for JOINED.               |
| after_values | JSONField     | State after the event.                               |
| timestamp    | DateTimeField | auto_now_add                                         |
| meta         | JSONField     | Extra context: mode, batch_size, batch_number        |

### queues.PickupEntry

| Field          | Type                  | Notes                                              |
|----------------|-----------------------|----------------------------------------------------|
| id             | BigAutoField          | PK                                                 |
| business       | FK → Business         | CASCADE                                            |
| order_number   | CharField             | Required. Provided by customer.                    |
| customer_name  | CharField             | Optional.                                          |
| phone          | CharField             | Optional. E.164 format. SMS sent here on ready.    |
| status         | CharField             | waiting / ready / picked_up                        |
| registered_at  | DateTimeField         | auto_now_add                                       |
| ready_at       | DateTimeField         | Set when staff marks Ready.                        |
| completed_at   | DateTimeField         | Set when staff marks Picked Up.                    |

### queues.PickupEventLog

Immutable. Never update rows. Only insert.

| Field      | Type          | Notes                                                   |
|------------|---------------|---------------------------------------------------------|
| id         | BigAutoField  | PK                                                      |
| business   | FK → Business | CASCADE                                                 |
| entry      | FK → PickupEntry | SET_NULL, nullable                                   |
| event_type | CharField     | registered / ready / picked_up / sms_sent / sms_failed  |
| timestamp  | DateTimeField | auto_now_add                                            |
| meta       | JSONField     | Extra context: order_number, to, error                  |

---

## State Machine

```
WAITING → CALLED → COMPLETED
WAITING → ABANDONED
WAITING → SKIPPED   (person mode only)
CALLED  → ABANDONED (no-show)
```

ALLOWED_TRANSITIONS (in queues/services.py):
```python
{
    "waiting":   {"called", "abandoned", "skipped"},
    "called":    {"completed", "abandoned"},
    "completed": set(),
    "abandoned": set(),
    "skipped":   set(),
}
```

Terminal states: COMPLETED, ABANDONED, SKIPPED

---

## URL Map

| URL                                      | View                                | Auth          | Notes                                        |
|------------------------------------------|-------------------------------------|---------------|----------------------------------------------|
| GET /                                    | RedirectView → /staff/login/        | None          | Homepage redirect                            |
| GET /q/<slug>/                           | customer.views.JoinView             | None          | Show join form (with intake questions)       |
| POST /q/<slug>/                          | customer.views.JoinView             | None          | Process join, save intake_answers            |
| GET /q/<slug>/confirmation/<id>/         | customer.views.ConfirmView          | None          | Live confirmation page                       |
| GET /q/<slug>/status/<id>/               | customer.views.CustomerStatusView   | None          | Public polling endpoint                      |
| POST /q/<slug>/response/<id>/            | customer.views.CustomerResponseView | None          | Customer response after abandoned/skipped    |
| GET /staff/login/                        | dashboard.views.StaffUnifiedLoginView | None        | Single login page with business picker       |
| GET /staff/<slug>/login/                 | dashboard.views.StaffLoginView      | None          | Redirects to /staff/login/?slug=<slug>       |
| GET /staff/<slug>/logout/                | dashboard.views.StaffLogoutView     | Session       | Clear session → /staff/login/                |
| GET /staff/<slug>/                       | dashboard.views.DashboardView       | Session/Super | Queue list with expandable intake rows       |
| GET/POST /staff/<slug>/settings/         | dashboard.views.SettingsView        | Session/Super | Settings + business type + intake questions  |
| POST /staff/<slug>/next/                 | dashboard.views.CallNextView        | Session/Super | Trigger call_next()                          |
| POST /staff/<slug>/complete-batch/       | dashboard.views.CompleteBatchView   | Session/Super | Settle called batch + call next              |
| POST /staff/<slug>/skip/<id>/            | dashboard.views.SkipEntryView       | Session/Super | waiting → skipped                            |
| POST /staff/<slug>/complete/<id>/        | dashboard.views.CompleteEntryView   | Session/Super | called → completed                           |
| POST /staff/<slug>/noshow/<id>/          | dashboard.views.NoShowEntryView     | Session/Super | called → abandoned (no-show)                 |
| GET /staff/<slug>/qr.png                 | dashboard.views.QRCodeView          | Session/Super | QR code PNG                                  |
| GET /api/queue/<slug>/status/            | dashboard.views.QueueStatusAPIView  | Session/Super | Staff polling endpoint (includes intake_answers) |
| GET /platform/                           | dashboard.views.PlatformDashboardView | Superuser   | Manage businesses                            |
| GET/POST /platform/login/                | dashboard.views.PlatformLoginView   | None          | Superuser login                              |
| GET /platform/logout/                    | dashboard.views.PlatformLogoutView  | Superuser     | Superuser logout                             |
| GET /q/<slug>/pickup/                    | customer.views.PickupJoinView       | None          | Pickup order registration form               |
| POST /q/<slug>/pickup/                   | customer.views.PickupJoinView       | None          | Process pickup registration                  |
| GET /q/<slug>/pickup/confirmation/<id>/  | customer.views.PickupConfirmView    | None          | Pickup confirmation page                     |
| POST /staff/<slug>/pickup/<id>/ready/    | dashboard.views.PickupReadyView     | Session/Super | Mark order ready, fire SMS if phone present  |
| POST /staff/<slug>/pickup/<id>/picked-up/| dashboard.views.PickupPickedUpView  | Session/Super | Mark order picked up                         |
| GET /api/pickup/<slug>/status/           | dashboard.views.PickupStatusAPIView | Session/Super | Pickup polling endpoint (waiting + ready)    |
| GET /health/                             | core.views.HealthCheckView          | None          | DB health probe                              |
| GET /admin/                              | Django admin                        | is_staff      | Full admin panel                             |

---

## Business Types

`business_type` is designed to be extensible. Current behaviour:

| Feature             | retail | clinic |
|---------------------|--------|--------|
| menu_url shown      | ✓      | ✗      |
| intake questions    | ✓      | ✓      |
| Queue modes         | both   | both   |
| Clinic-specific UI  | —      | planned |

Add clinic-specific blocks behind `{% if business.business_type == "clinic" %}` in templates.

---

## Intake Questions Flow

1. Staff adds questions to `business.intake_fields` via Settings page (JS add/remove list)
2. Customer join page renders one text input per question
3. On submit, answers saved as `QueueEntry.intake_answers` dict (`{question: answer}`)
4. Staff dashboard entry rows are tappable — expand to show intake_answers inline
5. `intake_answers` included in `/api/queue/<slug>/status/` JSON response

---

## SMS Flow

1. `QueueService.call_next()` calls `notifications.sms.TwilioSMSBackend.send()`
2. `TwilioSMSBackend` sends via Twilio REST API (synchronous HTTP call)
3. On success: logs SMS_SENT to QueueEventLog
4. On failure: logs SMS_FAILED, swallows exception, returns False
5. call_next() completes regardless of SMS outcome

---

## Pickup Flow

1. Customer visits `/q/<slug>/` — if `pickup_enabled=True`, sees "Track my order" form (tab or standalone)
2. Customer submits order number (+ optional name and phone) → `PickupService.register()` creates `PickupEntry`
3. Customer sees confirmation page — "We'll text you" if phone given, else "We'll call your name"
4. Staff dashboard shows pickup orders section — polling `/api/pickup/<slug>/status/` every 5 seconds
5. Staff taps **Ready** → `PickupService.mark_ready()` sets status=ready, sets ready_at, sends SMS if phone present
6. SMS outcome (sent/failed) logged to `PickupEventLog`
7. Staff taps **Picked up** → `PickupService.mark_picked_up()` sets status=picked_up, entry removed from active list

### Customer Join Page States

| queue_enabled | pickup_enabled | Result                                              |
|---------------|----------------|-----------------------------------------------------|
| True          | False          | Queue join form only (unchanged behaviour)          |
| False         | True           | Pickup form only                                    |
| True          | True           | Tab toggle — "Join the queue" / "Track my order"    |
| False         | False          | "Not currently accepting customers" message         |

---

## Deployment

- Platform: Railway (railway.json + Procfile)
- Build: nixpacks auto-detects Python, runs `collectstatic`
- Release: `python manage.py migrate --noinput` (in Procfile release command)
- Static files: WhiteNoise with CompressedManifestStaticFilesStorage
- Health check: GET /health/ — probes DB connection
- Required env vars: DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, DEBUG, DB_*, TWILIO_*
