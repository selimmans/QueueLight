# TASKS.md — Queue Light

Update this file at the end of every session. Never commit this file alone.

---

## PHASE 1 — Scaffold and docs
- [x] Project structure, settings, docs, git init

## PHASE 2 — Core models
- [x] Business, StaffPhone, QueueEntry, QueueEventLog models + migrations

## PHASE 3 — QueueService state machine
- [x] join(), call_next(), abandon(), skip() with ALLOWED_TRANSITIONS guard

## PHASE 4 — SMS backend
- [x] TwilioSMSBackend, SMSTestBackend, failure logging

## PHASE 5 — Customer join page
- [x] JoinView, ConfirmView, phone validation, rate limiting, templates

## PHASE 6 — Staff dashboard
- [x] StaffLoginView, DashboardView, CallNextView, session auth, polling

## PHASE 7 — QR code
- [x] QR PNG generation, cached, displayed on staff dashboard

## PHASE 8 — Wait time range
- [x] ~min–max range estimate on confirmation page

## PHASE 9 — Live confirmation + public status API
- [x] CustomerStatusView polling endpoint, live page, called overlay, abandoned response

## PHASE 10 — Post-call actions
- [x] complete(), no_show(), complete_batch(), skip(), batch intercept UI

## PHASE 11 — Settings page
- [x] SettingsView: batch size, avg time, SMS template, mode toggle, closing soon, clear queue

## PHASE 12 — Platform dashboard
- [x] Superuser login/logout, create/activate/delete businesses
- [x] Staff phone management in settings page
- [x] Menu URL field on business (confirmation page shows "View Menu" if set)
- [x] is_closing flag, closing message on join page

## PHASE 13 — UX improvements
- [x] Single staff login page /staff/login/ with business picker
- [x] Country calling code prefix on phone inputs (join + staff login)
- [x] Superusers bypass staff phone auth (Open button goes straight to dashboard)
- [x] Root URL / redirects to /staff/login/
- [x] Brand colours: Primary, Accent, Borders (labelled hex inputs on platform dashboard)

## PHASE 14 — Business type + intake questions
- [x] Business.business_type field (retail / clinic), default retail
- [x] Business.intake_fields JSONField (list of question strings)
- [x] QueueEntry.intake_answers JSONField (dict of question → answer)
- [x] Settings page: business type toggle, intake questions add/remove
- [x] menu_url hidden for clinic type
- [x] Join page renders intake_fields dynamically, saves answers on submit
- [x] Staff dashboard: expandable entry rows showing intake_answers
- [x] Admin panel: business_type, intake_fields, intake_answers exposed

## PHASE 15 — Deployment prep
- [x] gunicorn added to requirements.txt
- [x] Procfile (web + release command for migrations)
- [x] railway.json (health check at /health/, restart policy)
- [x] CSRF_TRUSTED_ORIGINS env var support in settings

## PHASE 17 — Production deploy
- [x] GitHub repo created and code pushed (selimmans/QueueLight)
- [x] Deployed to Railway at web-production-d59e3.up.railway.app
- [x] Procfile release → preDeployCommand migration fix
- [x] ALLOWED_HOSTS updated to include healthcheck.railway.app
- [x] Superuser created on production DB
- [x] Business type selector added to platform create form
- [x] Business picker reverted to native select on staff login
- [x] Batch intercept: shows on page load, poll no longer rebuilds during active selection

## PHASE 16 — UI redesign + polish
- [x] DM Serif Display font throughout (join, confirmation, staff dashboard, login)
- [x] Customer pages: white background, card shadows, clean grey palette
- [x] Staff dashboard: dark #111 header + stats bar, black Call Next, gold called badges
- [x] Login page: no blue, black Sign in button, custom dropdown chevron
- [x] Settings page: no brand colour on buttons/focus states
- [x] All emojis removed from templates
- [x] Leave queue button on confirmation page (POST → QueueService.abandon → redirect join)
- [x] Confirmation "In queue" stat fixed — now shows real waiting count not batch_size
- [x] waiting_total added to CustomerStatusView JSON response (live-updates via poll)

---

## Pending — needs YOU

| # | Task | Notes |
|---|------|-------|
| 1 | Create Twilio account | Get SID, auth token, and a sender phone number |
| 2 | Set `twilio_from_number` on each business | Via Django admin after deploy |
| 3 | Deploy to Railway | Connect repo, set env vars below, run migrations |
| 4 | Set env vars on Railway | See list below |
| 5 | Set `is_active=True` on businesses | Via platform dashboard after deploy |
| 6 | Run `python manage.py changepassword admin` | Admin password was cleared during dev |

### Required env vars for Railway
```
DJANGO_SECRET_KEY=<generate: python3 -c "import secrets; print(secrets.token_urlsafe(50))">
DJANGO_ALLOWED_HOSTS=<your-app>.up.railway.app
CSRF_TRUSTED_ORIGINS=https://<your-app>.up.railway.app
DEBUG=False
DB_NAME=railway
DB_USER=postgres
DB_PASSWORD=<from Railway Postgres plugin>
DB_HOST=<from Railway Postgres plugin>
DB_PORT=5432
TWILIO_ACCOUNT_SID=<from Twilio>
TWILIO_AUTH_TOKEN=<from Twilio>
TWILIO_FROM_NUMBER=<shared sender number, e.g. +18254609913 — used for any business with no twilio_from_number set>
DJANGO_TIME_ZONE=America/Toronto
```

---

## Backlog

- [ ] Business logo upload — placeholder shown on join/confirmation page, upload via admin or settings
- [ ] Late arrival banner on staff dashboard (KNOWN_ISSUES)
- [ ] Analytics UI (data is captured in QueueEventLog, not surfaced)
- [ ] Clinic-specific dashboard features (expandable intake review, patient notes)
- [ ] Self-serve business onboarding (currently superuser-only)
- [ ] Redis cache for QR PNG in multi-worker deploys
- [ ] Per-country phone validation (currently uses business.country, CA default)
- [x] Twilio shared sender fallback — if business.twilio_from_number is blank, fall back to TWILIO_FROM_NUMBER env var (so all businesses can share one number for a pilot)
- [ ] Public queue browser — /join/ listing all active businesses so customers can find and join without a QR code
