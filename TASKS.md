# TASKS.md — Queue Light

Update this file at the end of every session. Never commit this file alone.

---

## PHASE 1 — Scaffold and docs
Commit: `init: project scaffold and docs`

- [x] Create Django project structure (config/, businesses/, queue/, notifications/, customer/, dashboard/, core/)
- [x] Create config/settings.py adapted from Clove
- [x] Create AGENT.md
- [x] Create TASKS.md
- [x] Create ARCHITECTURE.md
- [x] Create TESTING.md
- [x] Create DEFINITION_OF_DONE.md
- [x] Create KNOWN_ISSUES.md
- [x] Create requirements.txt
- [x] Create .env.example
- [x] Create manage.py, wsgi.py, config/__init__.py, config/urls.py
- [x] Create __init__.py stubs for all apps
- [x] Initialise git, make first commit

---

## PHASE 2 — Core models
Commit: `feat: core models and migrations`

- [x] businesses app: Business model
- [x] businesses app: StaffPhone model
- [x] queue app: QueueEntry model
- [x] queue app: QueueEventLog model
- [x] Run migrations and verify
- [x] Register models in Django admin
- [x] Update TASKS.md and ARCHITECTURE.md

---

## PHASE 3 — QueueService state machine
Commit: `feat: QueueService state machine, SMS backend, customer and staff pages`

- [x] queues/services.py: QueueService with ALLOWED_TRANSITIONS guard
- [x] join() — batch and person mode, position + batch_number assignment
- [x] call_next() — locks rows, marks CALLED, sends SMS outside atomic block
- [x] abandon() and skip() (skip raises in batch mode)
- [x] queues/tests/test_services.py — full transition + SMS failure coverage

---

## PHASE 4 — SMS backend
Commit: `feat: QueueService state machine, SMS backend, customer and staff pages`

- [x] notifications/sms.py: TwilioSMSBackend — catches own exceptions, returns True/False
- [x] SMSTestBackend stub for tests
- [x] SMS failure logs SMS_FAILED and does not crash call_next()
- [x] notifications/tests/test_sms.py — Twilio mock + failure path tests

---

## PHASE 5 — Customer join page
Commit: `feat: QueueService state machine, SMS backend, customer and staff pages`

- [x] customer/views.py: JoinView (GET + POST), ConfirmView (GET)
- [x] Phone validation via phonenumbers using business.country (ISO 3166-1 alpha-2)
- [x] E.164 storage, rate limiting 20/hr per IP (cache-based)
- [x] Inactive business → 404 on GET and POST
- [x] customer/templates/customer/join.html — mobile-first, accent bar, field-level errors
- [x] customer/templates/customer/confirmation.html — batch number or position, estimated wait
- [x] URL routing: /q/<slug>/ and /q/<slug>/confirmation/<int:entry_id>/
- [x] Business.country field (migration 0003), Business.avg_service_minutes (migration 0004)
- [x] Business.sms_template field with {business_name}/{customer_name} placeholders (migration 0002)
- [x] customer/tests/test_views.py — 16 tests

---

## PHASE 6 — Staff dashboard
Commit: `feat: QueueService state machine, SMS backend, customer and staff pages`

- [x] dashboard/views.py: StaffLoginView, StaffLogoutView, DashboardView, CallNextView, QueueStatusAPIView
- [x] Session auth: business_id + staff_phone_id, cross-business protection
- [x] dashboard/templates/dashboard/login.html — phone entry, mobile-first
- [x] dashboard/templates/dashboard/queue.html — queue list, last-called banner, 5-second polling
- [x] URL routing: /staff/<slug>/login/, /staff/<slug>/logout/, /staff/<slug>/, /staff/<slug>/next/
- [x] /api/queue/<slug>/status/ JSON endpoint (waiting, called_last, mode, batch_size, avg_service_minutes)
- [x] dashboard/tests/test_views.py — 18 tests
- [x] 81 tests passing across all apps

---

## PHASE 7 — QR code
Commit: `feat: QR code generation and serving`

- [ ] GET /staff/<slug>/qr.png — generate QR pointing to /q/<slug>/
- [ ] Display on staff dashboard
- [ ] Update TASKS.md

---

## PHASE 8 — Polish and handover
Commit: `chore: final polish and doc updates`

- [ ] Show wait time as a range (~15–30 min) rather than single number
- [ ] Full manual test on mobile
- [ ] KNOWN_ISSUES.md — document deferred decisions
- [ ] Update all docs to final state
