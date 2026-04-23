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

- [ ] businesses app: Business model
- [ ] businesses app: StaffPhone model
- [ ] queue app: QueueEntry model
- [ ] queue app: QueueEventLog model
- [ ] Run migrations and verify
- [ ] Register models in Django admin
- [ ] Update TASKS.md and ARCHITECTURE.md

---

## PHASE 3 — QueueService state machine
Commit: `feat: QueueService state machine`

- [ ] Implement QueueService in queue/services.py
- [ ] ALLOWED_TRANSITIONS guard pattern
- [ ] join() method
- [ ] call_next() method (batch and person mode)
- [ ] abandon() method
- [ ] skip() method (person mode only)
- [ ] Unit tests for all transitions (mock Twilio)
- [ ] Update TASKS.md

---

## PHASE 4 — SMS backend
Commit: `feat: Twilio SMS backend`

- [ ] notifications/sms.py: TwilioSMSBackend
- [ ] Test stub / mock for tests
- [ ] Error handling: log SMS_FAILED, do not crash call_next()
- [ ] Update TASKS.md

---

## PHASE 5 — Customer join page
Commit: `feat: customer join and confirmation pages`

- [ ] customer/views.py: JoinView (GET + POST)
- [ ] customer/views.py: ConfirmView (GET)
- [ ] customer/templates/customer/join.html
- [ ] customer/templates/customer/confirmation.html
- [ ] URL routing: /q/<slug>/
- [ ] Mobile-optimised layout
- [ ] Update TASKS.md

---

## PHASE 6 — Staff dashboard
Commit: `feat: staff dashboard with polling`

- [ ] Staff auth: StaffLoginView, StaffLogoutView
- [ ] DashboardView: queue list
- [ ] CallNextView: triggers call_next()
- [ ] QueueStatusAPIView: JSON endpoint for polling
- [ ] dashboard/templates/dashboard/login.html
- [ ] dashboard/templates/dashboard/queue.html
- [ ] 5-second polling via fetch()
- [ ] Shows last called batch/person at top
- [ ] Update TASKS.md

---

## PHASE 7 — QR code
Commit: `feat: QR code generation and serving`

- [ ] Generate QR code at Business creation
- [ ] Store QR code or generate on-the-fly
- [ ] GET /staff/<slug>/qr.png
- [ ] Display on staff dashboard
- [ ] Update TASKS.md

---

## PHASE 8 — Polish and handover
Commit: `chore: final polish and doc updates`

- [ ] URL routing review
- [ ] KNOWN_ISSUES.md — document deferred decisions
- [ ] Full manual test on mobile
- [ ] Update all docs to final state
