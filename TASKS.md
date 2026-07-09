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

## PHASE 18 — Pickup notifications
- [x] Business.queue_enabled (default True) + Business.pickup_enabled (default False) fields + migration
- [x] Business.pickup_notification_message field (blank → falls back to hardcoded default)
- [x] PickupEntry model (id, business, order_number, customer_name, phone, status, registered_at, ready_at, completed_at)
- [x] PickupEventLog model (business, entry FK, event_type, timestamp, meta)
- [x] PickupService: register(), mark_ready(), mark_picked_up(); SMS via TwilioSMSBackend on mark_ready()
- [x] Customer join page: 4 states (queue_only / pickup_only / both / inactive) with tab toggle for both
- [x] Pickup join page (/q/<slug>/pickup/) + pickup confirmation page
- [x] Staff dashboard: pickup orders section with Ready / Picked up buttons, 5s polling
- [x] Settings page: Features section — queue toggle (blocked when queue non-empty), pickup toggle, pickup SMS message field
- [x] Platform create form: queue_enabled / pickup_enabled dropdowns
- [x] Django admin: Business fieldsets updated; PickupEntry + PickupEventLog registered
- [x] 102 tests passing (31 new pickup tests)

## PHASE 19 — Dashboard tab system
- [x] DashboardView passes `dashboard_mode` context variable ("queue_only" / "pickup_only" / "both" / "inactive")
- [x] queue.html: 4-state layout — queue_only (solo panel, no tab bar), pickup_only (solo panel, no tab bar), both (tab bar with Queue + Pickup buttons), inactive (inactive-notice message)
- [x] Tab bar: dark #1a1a1a strip below header; tabBtnQueue / tabBtnPickup buttons; active tab has brand colour underline
- [x] Tab panels: `.tab-panel { display:none }` / `.tab-panel.active { display:block }` / `.tab-panel.solo { display:block }` for single-feature modes
- [x] sessionStorage persistence keyed by slug (`activeTab_<slug>`) — survives page refresh / poll redirects
- [x] Tab-aware polling: `queueTimer` / `pickupTimer` module-level vars; `switchTab()` clears both before starting the active one; single-feature modes poll directly without switchTab
- [x] Stats bar moved inside queue panel (only visible on queue tab in "both" mode)
- [x] PickupStatusAPIView response shape updated: `{active_orders: [{id, order_number, customer_name, status, registered_at, minutes_waiting}], total_active: N}`
- [x] `minutes_waiting` calculated server-side (avoids JS timezone issues)
- [x] TestDashboardMode: 7 tests verifying HTML/context for all 4 states
- [x] TestPickupStatusAPI: updated for new response shape + added minutes_waiting and response_shape tests
- [x] 149 tests passing

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

## PHASE 20 — Read-only POS integrations (Clover + Square)
- [x] `rapidfuzz` + `requests` added to requirements.txt
- [x] Business model: `pos_type` (none/clover/square), `pos_api_token`, `pos_merchant_id` fields + migration
- [x] PickupEntry model: `pos_order_id`, `pos_order_items`, `pos_match_confidence` fields + migration
- [x] `notifications/pos_integration.py`: `POSIntegration`, `CloverIntegration`, `SquareIntegration` — read-only, never writes to POS
- [x] `POST /api/pickup/<slug>/match/` — public, rate-limited (10/min/IP), fuzzy name matching via rapidfuzz `token_sort_ratio`, threshold 0.75
- [x] Pickup join page redesigned for POS flow: name-first, JS match call, confirmation card ("Is this your order? [items]"), "That's not me" fallback, localStorage prefill for returning customers
- [x] Standard (non-POS) pickup flow unchanged
- [x] Staff dashboard pickup rows show POS order items inline (both SSR initial and polled JS rendering)
- [x] `PickupStatusAPIView` response includes `pos_order_items`
- [x] Settings page: POS Integration section (admin only, pickup_enabled only) — POS type selector, merchant ID + token fields per provider, "Test connection" button via async JSON call
- [x] `SettingsView`: `save_pos` and `test_pos_connection` actions
- [x] 19 new tests (Clover, Square, POSIntegration.match_customer, /api/pickup/<slug>/match/)
- [x] `conftest.py` autouse `clear_django_cache` fixture (fixes pre-existing cache bleed between tests)
- [x] 168 tests passing

## PHASE 21 — Extended POS integrations + multi-signal order matching

- [x] Business model: added `POS_TOAST`, `POS_LIGHTSPEED` to `pos_type` choices; added `toast_client_id`, `toast_client_secret` CharField; added `default_identifier` CharField (name/order_number/phone) + migration
- [x] `ToastIntegration`: OAuth2 client credentials flow, 50-min in-process token cache (`_toast_token_cache`), fetches `ordersBulk` endpoint, extracts name from `checks[0].customer.firstName+lastName`
- [x] `LightspeedIntegration`: API key Bearer auth, `Sale.json` endpoint, extracts `Sale.name` and `SaleLines.SaleLine[].Item.description` (handles single-item dict vs list)
- [x] `POSIntegration` dispatcher updated to route Toast + Lightspeed
- [x] `POSIntegration.match_customer()` upgraded: now accepts `customer_name`, `phone`, `order_number`; priority: phone exact → order number exact → name fuzzy; new response shape: `{matched, multiple, orders: [{order_id, order_reference, items, confidence}], + legacy fields}`
- [x] `POST /api/pickup/<slug>/match/` updated: accepts any of name/phone/order_number; returns new shape including `orders[]` and `multiple`; legacy `order_id`/`items`/`confidence` retained for backward compat
- [x] Pickup join page: primary field driven by `business.default_identifier`; toggle links to switch to any other identifier; all three fields sent on search; localStorage saves name+phone+order on confirm; auto-search on return visit uses active primary field
- [x] Settings page: Toast (GUID + Client ID + Client Secret) and Lightspeed (Account ID + API Key) field sections in POS Integration; `default_identifier` selector shown when POS is active
- [x] 14 new tests (Toast, Lightspeed, phone/order_number matching, new API response shape); 182 tests passing

## PHASE 22 — Admin-only join page field configuration

- [x] Business model: 6 new BooleanFields — `field_name_enabled` (True), `field_name_required` (True), `field_order_number_enabled` (False), `field_order_number_required` (False), `field_phone_enabled` (True, no UI toggle), `field_phone_required` (False) + migration `0014`
- [x] Settings page: new "Join page fields" section (admin + pickup_enabled only) — Show/Hide and Required/Optional toggles per field; phone row is Required/Optional only (always shown)
- [x] `save_join_fields` POST action in `SettingsView` — blocked if active (waiting/ready) pickup entries exist; non-superuser ignored
- [x] Pickup join template: fields rendered/hidden/required per config; optional phone shows helper hint "Add your number to get a text..."
- [x] Standard POST validation: respects `field_*_required` — blocks submission with error, auto-generates order_number when disabled/optional+empty
- [x] Pickup confirmation page: no-phone message updated to "We'll call your name when your order is ready."
- [x] 25 new tests (field config saves, active entry blocks, non-admin blocked, rendering, validation, no-phone entry + confirmation); 208 tests passing
- [x] Reference presets (Retail / Clinic / Order-number counter) documented in ARCHITECTURE.md

## PHASE 22b — Phone always required on pickup join form

- [x] Phone removed from join field config — not configurable, always required
- [x] Settings UI: phone row now shows "Always required" static text (no toggle)
- [x] `save_join_fields` action: `field_phone_required` no longer saved
- [x] All three pickup join form paths (standard, POS-confirmed, POS-fallback): phone `required` attribute enforced in HTML + server-side validation
- [x] Fixes known issue: POS flow phone step lacked `required` attribute
- [x] Tests updated: `test_pickup_views.py` and `test_join_field_config.py` rewritten for required phone; 206 tests passing

## PHASE 23 — Show unregistered POS orders on pickup dashboard

- [x] `PickupStatusAPIView`: when `pos_type != 'none'`, calls `POSIntegration.get_recent_orders()`, filters out orders whose `pos_order_id` matches an active `PickupEntry`, returns remainder as `unregistered_orders`
- [x] API response extended: `unregistered_orders: [{pos_order_id, customer_name, items, ordered_at, minutes_ago}]` + `total_unregistered`; existing `active_orders` / `total_active` unchanged
- [x] `_minutes_ago_from_pos_ts()` helper: handles int (ms epoch / Clover), ISO string (Square / Toast / Lightspeed), and `None`
- [x] POS fetch wrapped in try/except — any POS failure returns empty list, API still returns 200
- [x] Dashboard template: "Not yet scanned" section with greyed entries, 📢 badge, "Call name" label; hidden when empty; only rendered when `business.pos_type != 'none'`
- [x] `pollPickup()` updated to render `unregistered_orders` from API and show/hide the section
- [x] 8 new tests (no-POS empty, order returned, registered excluded, shape, POS failure, ISO timestamp, ms timestamp, response keys); 214 tests passing

## PHASE 24 — POS analytics fields on PickupEntry

- [x] `PickupEntry` model: 3 new fields — `pos_order_created_at` (DateTimeField, nullable), `pos_order_total` (PositiveIntegerField cents, nullable), `pos_order_reference` (CharField) + migration `queues/0007`
- [x] All 4 POS integrations updated to include `order_total` (cents) and `order_reference` in normalised order dicts (Clover: `order.total`; Square: `total_money.amount` + `reference_id`; Toast: `check.totalAmount` ×100 + `displayNumber`; Lightspeed: `calcTotal` ×100 + `receiptNum`)
- [x] `match_customer()` orders array extended with `ordered_at` and `order_total` so the customer's browser can pass them as hidden form fields
- [x] `PickupJoinView` POS-confirmed path: extracts `pos_ordered_at`, `pos_order_total`, `pos_order_reference` from POST, parses timestamp (ISO + ms-epoch) and int total, stamps all 3 on `PickupEntry`
- [x] `PickupStatusAPIView` `active_orders` response now includes `pos_order_created_at`, `pos_order_total`, `pos_order_reference`; `unregistered_orders` now includes `order_total` and `order_reference`
- [x] 8 new tests (Clover/Square/Toast/Lightspeed analytics fields, match_customer includes fields, unregistered order shape, active order analytics nulls/values); 222 tests passing

## PHASE 25 — Kotn Cup 26 pop-up (one-off branded event, Trinity Bellwoods Toronto, Fri July 10)

- [x] `customer/views.py`: `KOTN_POPUP_SLUG = "kotn-cup-toronto"` constant gates all one-off logic; `PickupJoinView`/`PickupConfirmView` pick branded templates for this slug
- [x] Name field repurposed as "name to embroider", capped at 8 chars (`KOTN_NAME_MAX_LENGTH`), enforced client-side (`maxlength` + live JS counter, defensively clamps on overflow) and server-side
- [x] Shirt size added as a required two-option field (Short Sleeve / Long Sleeve), stored in `PickupEntry.intake_answers["Size"]` — no model/migration change, reuses existing JSONField
- [x] Patch number added as a required numeric field, stored in `intake_answers["Patch"]` — no model/migration change
- [x] New branded templates: `customer/templates/customer/pickup_join_kotn.html`, `pickup_confirmation_kotn.html` — maroon/gold palette pulled from `business.logo_colour`/`colour_accent`, Archivo Black display font, patch/size/name/phone fields, live ready-status polling (reuses existing `pickup_status` endpoint, unchanged)
- [x] Dashboard (`dashboard/templates/dashboard/queue.html`): pickup rows now also show `intake_answers.Patch` and `intake_answers.Size` inline (both SSR initial block and JS `renderPickupEntry` poll path), same treatment as existing `pos_order_items`
- [x] Order number auto-assigned server-side (never typed by customer) so staff know what to write on the physical shirt tag
- [x] Verified end-to-end in browser preview: join → validation (name >8 chars, out-of-range patch both client- and server-side) → confirmation page → dashboard shows name/patch/size/order number inline → "Ready" tap flips status, fires SMS (Twilio call executes correctly; only failed in dev because sandbox to/from numbers matched), customer confirmation page flips to ready overlay via existing poll
- [x] 230 existing tests still pass — one dashboard test caught an over-broad first draft (order-number hiding leaked to all businesses); fixed by scoping to `kotn-cup-toronto` only
- [x] Number ranges fixed: `KOTN_PATCH_MIN/MAX = 1/6` (only 6 physical patch designs); added `KOTN_ORDER_MIN/MAX = 1/300`. Order number is now auto-assigned sequentially (1–300) inside `transaction.atomic()` with `Business.objects.select_for_update()` locking the business row, so concurrent joins at event start can't collide. Capacity overflow (>300) shown as a `global_error` on the join page ("Sorry, we're at capacity..."), entry not created. Patch hint text in `pickup_join_kotn.html` already used template variables (`{{ kotn_patch_min }}`–`{{ kotn_patch_max }}`), so it updated automatically.
- [x] 11 new tests added in `customer/tests/test_kotn_popup.py`: branded template rendering, name length cap, patch range/non-numeric validation, missing size, valid submission, sequential order-number assignment (1, 2, 3...), customer cannot override order_number, capacity-reached blocks new entries, other-business order numbers don't collide. 241 tests passing.
- [x] Committed (`b064a69`) and pushed to `main`. Railway auto-deployed successfully.
- [x] `kotn-cup-toronto` Business row created in **production** (id 4), `is_active=True`, `pickup_enabled=True`, brand colours set to maroon/gold (`#5c1a24` / `#d9b35a` / `#e8d9c4`) to match the local dev design. `twilio_from_number` left blank — uses the shared `TWILIO_FROM_NUMBER=+18254609913` env var fallback like the other 3 live businesses.
- [x] **Important gotcha discovered this session:** `railway run` / `railway shell` (executed from local terminal) silently connected to the WRONG Postgres database — showing stale/unrelated data (`demo`, `demo-cafe`, `moe-joes`) that doesn't match the real live site's businesses (`ridge-eats`, `the-local-by-masrawy`, `moe-joe-s`). Root cause not fully diagnosed (suspected stale internal-network tunnel/DNS cache from another linked Railway project on this machine). `railway connect Postgres --environment production` (a direct psql tunnel) reliably reaches the correct DB and was used for all production writes instead. **Do not trust `railway run`/`railway shell` output against production without cross-checking via `railway connect` or the dashboard first.**
- [x] End-to-end verified on live production URL: join flow (patch 1-6 validation, order name still returns sequential order numbers correctly per-business, e.g. first kotn entry got "Order #1" not a raw pk), dashboard shows the entry, "Ready" button flips status and fires the SMS send attempt correctly (event log confirms `PickupService.mark_ready` and Twilio call both ran). Test entry, its event log, and the temporary test staff phone were deleted afterward — production has 0 kotn pickup entries and 0 staff phones as of end of session.
- [ ] **SMS delivery not yet confirmed with a real recipient.** The one delivery attempt failed with `'To' and 'From' number cannot be the same` because the test used `+18254609913` as both sender and recipient (repeating the same mistake flagged in the prior handoff — that number is the shared Twilio *sender*, not a valid test recipient). Needs a real different phone number to confirm actual delivery before Friday.
- [ ] **No real staff phone numbers registered yet** for `kotn-cup-toronto` in production (the one used for testing was deleted). Staff working the event need real phone numbers added via Django admin or a DB insert before Friday, or they won't be able to log into `/staff/login/`.

## PHASE 25b — Kotn Cup 26: multi-shirt orders + full design-handoff-2 redesign (DEPLOYED)

- [x] New client design handoff (`design_handoff_kotn_pop_up_shop 2/`) fully implemented locally: 6 patches now multi-select (up to 2 per shirt, `KOTN_PATCH_MAX_PER_SHIRT`), repeatable shirt builder (one active/expanded shirt at a time, others collapse to summary rows, add/remove), phone collected once at the end for the whole order, Sohne Dreiviertelfett print font, sponsor logo grid (6 marks), scrolling ticker footer, Kotn Cup Toronto badge, 25s kiosk auto-reset preserved from PHASE 25.
- [x] Data model (still no migration): `PickupEntry.intake_answers["Shirts"]` is now a list of `{tag, patches: [{name, crest}], sleeve, name}`, one entry per order (one phone, one SMS, one dashboard row) but one **tag number per shirt** — tags are global/sequential across the whole event (1–300), not per-order, so a 2-shirt order consumes 2 consecutive tags. `order_number` is a single tag ("003") or a range ("003–004") for display.
- [x] `customer/views.py`: new `PickupJoinView._post_kotn()` handles the whole multi-shirt submission (JSON-encoded `shirts` + `phone` in one POST); old single-shirt kotn branches removed from the generic standard-path POST handler.
- [x] Tag assignment: locks the Business row, computes `next_start` from the max tag seen across all existing entries' `Shirts` lists (falling back to legacy `order_number` for pre-multi-shirt entries), reserves N consecutive tags atomically, rejects the **whole order** if it would exceed 300 (not partial fulfillment).
- [x] **Migrated the 2 real production orders** (ids 459/460, `order_number` "001"/"002", placed by real customers before this change) from the old flat `Patch`/`Size` intake_answers shape to the new `Shirts` list shape, so tag-counting and the new dashboard card both handle them correctly. Did this directly via `railway connect Postgres --environment production` SQL UPDATE — verified before/after.
- [x] Dashboard: new `.kotn-card` layout scoped to `business.slug == "kotn-cup-toronto"` only (both SSR block and JS `renderKotnEntry`, mirroring `renderPickupEntry`'s pattern) — one always-expanded card per order (no click-to-expand), every shirt in the order listed inline with crest thumbnail(s), single Mark Ready/Picked-up button for the whole order. `PickupStatusAPIView` JSON gained a `phone` field (was missing) so the card can show it.
- [x] New static assets copied to `customer/static/customer/kotn/`: qatn-logo-maroon/green, kotn-cup-toronto-badge, ticker-panel-maroon/gold, 6 sponsor PNGs (pre-alpha-processed by the designer — do NOT use the raw ones downloaded to `~/Desktop/Kotn Cup/Sponsor Logos - Official/` earlier, those still have baked-in white backgrounds except casa_del_rey option2), TestSohne-Dreiviertelfett.otf.
- [x] Ran `collectstatic` locally after adding assets (required — see PHASE 25 gotcha about `CompressedManifestStaticFilesStorage` needing a fresh manifest for any new static file).
- [x] `customer/tests/test_kotn_popup.py` fully rewritten for the multi-shirt POST contract (17 tests: patch cap, sleeve/name validation, single vs multi-shirt tag assignment, global tag pool across orders, legacy-entry tag counting, capacity all-or-nothing rejection, cross-business isolation). One pre-existing test in `test_pickup_views.py` updated for the pickup-only redirect behavior added in PHASE 25. 247 tests passing.
- [x] Verified end-to-end in local browser preview: 2-shirt order build (collapse/expand, 2-patch select, add shirt) → phone step with correct order summary → multi-tag queue screen (tags 001/002, sponsor grid, ticker, badge all rendering) → marked ready → stepper/logo/tags/instruction line all correctly re-themed green, no full-page reload → dashboard card showed both shirts with crest thumbnails and one Picked-up button. Test data cleaned up after.
- [x] Committed (`fc4579e`) and pushed with explicit user go-ahead ("push everything I'm happy with it right now"). Railway deploy confirmed SUCCESS, live UI verified ("Pick Your Patch" present on production).
- [ ] Real sponsor logo files were separately downloaded to `~/Desktop/Kotn Cup/Sponsor Logos - Official/` for reference earlier in the day — those are NOT what's wired into the app; the app uses the designer's own pre-processed `sponsor-*.png` files from the handoff assets folder.

## PHASE 25c — Kotn Cup 26: perf fixes, ticker/badge polish, garment sizes (DEPLOYED)

- [x] **Root-caused and fixed intermittent ticker/badge flash.** Not a CSS/JS bug — every Kotn image asset was client-supplied at raw print resolution (ticker panels 26160×2616px shown at 34px tall; badge 7946×8105px shown at 62px tall; crests/sponsors similarly oversized), 1.5–1.9MB each. The JS reveal-gating added for the ticker (opacity:0 until images decode, 1.5s safety timeout) was itself getting outraced by real-world load time on non-instant connections, forcing the ticker visible before it was actually ready — the same flash, just delayed. Fixed by resizing every Kotn PNG to ~4x its largest on-screen display size via Pillow/LANCZOS (`customer/static/customer/kotn/*.png`). Footer payload (badge + 2 ticker panels) dropped from ~5MB to ~63KB; all 18 PNGs combined from ~8-9MB to ~430KB. No visible quality loss at display size — verified in browser. Commit `1b682ac`.
- [x] Removed the redundant "Kotn Cup 26 Toronto" boxed badge image between the sponsor grid and the ticker on both queue/ready screens per explicit client instruction — the ticker's own scrolling panels already carry the same wordmark/قطن marks, so showing both was repetitive. Deleted the `<img>` and its own margin only; did not touch ticker position/size/animation or add compensating spacing (the wrapper div already had the same 26px margin used elsewhere in the footer, so removal alone gave the correct rhythm). Page is intentionally shorter now — that's correct, not a bug. Commit `e81ee50`.
- [x] **Self-hosted all 4 font families** (Anton, Staatliches, Amiri 700 arabic-subset, Inter variable-weight) — was loading from Google Fonts CDN via `media=print`/`onload` async trick, but that only helps repeat-visit caching, and **every customer scans the QR on their own personal phone** (no shared-kiosk cache benefit — this was a wrong assumption caught by the user). Downloaded latin/arabic-subset WOFF2s directly from fonts.gstatic.com (~171KB total across all 4 families — Inter's 5 weights all resolve to one shared variable-font file), stored in `customer/static/customer/kotn/fonts/`, declared local `@font-face` rules, preloaded via `<link rel="preload" as="font">`. Zero external font requests now; `curl` on production confirms no `fonts.googleapis.com` references remain. Commit `79b0897`.
- [x] **Added garment Size (XS/S/M/L/XL/XXL) as a new required per-shirt field**, alongside existing patch/sleeve/name — `KOTN_GARMENT_SIZES` constant in `customer/views.py`, `.size-btn` row in the shirt builder (6-option wrapping button grid, distinct from the existing 2-option sleeve toggle), validated server-side in `_post_kotn`, stored as `shirt["size"]` (display name, e.g. "XL") in the `Shirts` list. Shown in: shirt builder summary rows, phone-step order summary, both confirmation screens (single- and multi-tag layouts), and the dashboard card. Legacy entries without a stored size (the 2 migrated real orders, pre-this-change) just omit the field in display — no error. Commit `79b0897`.
- [x] 249 tests passing (added `test_invalid_size_rejected`, `test_size_is_stored`; updated `_shirt()` test helper to include `size`).
- [x] All of the above verified live on production after each deploy (curl checks + one full browser walkthrough for the ticker/badge fix).
- [ ] **Not yet verified in a real phone browser on real event WiFi** — everything above was checked via curl (headers/content) and the Preview tool's headless browser, not an actual phone. Worth a real-device smoke test before Friday given the perf work was specifically motivated by "every customer's own phone, cold cache."
- [ ] Sleeve length (Short/Long) and garment Size (XS-XXL) are now two separate selectors — confirm with the client this is the intended garment spec (i.e., a customer picks a sleeve style AND a size, not one combined field) before the event, since this was added directly from a user request mid-session, not from a designer-reviewed spec like the rest of PHASE 25b.

## PHASE 25d — Kotn Cup 26: patch crest reminders + dashboard grouping (DEPLOYED)

- [x] Patch/crest thumbnail(s) now shown on the phone-entry step (`pickup_join_kotn.html` `renderOrderSummary()`) as a visual reminder next to each shirt's text summary, right before the customer submits their phone number. Commit `6a87133`.
- [x] Patch/crest thumbnail(s) also added to the waiting/ready confirmation screens (`pickup_confirmation_kotn.html`) — both the multi-tag `.tag-card` layout and the single-shirt summary layout, verified in both waiting (maroon) and ready (green) themes. Commit `ba25617`.
- [x] Pickup dashboard now splits active orders into two visually distinct sections — "To Prepare" (waiting, grey header) and "Ready for Pickup" (ready, green header) — instead of interleaving both statuses in one list. Implemented for both the Kotn card layout and the generic (non-Kotn) entry layout, in the initial server render (`DashboardView` now passes `pickup_waiting`/`pickup_ready` in addition to `pickup_entries`) and the live 5s poll re-render (`renderPickupState()` now groups `_activeOrders` by status client-side). Verified locally on both kotn-cup-toronto and demo-cafe (POS "Not yet scanned" section unaffected). Commit `7f6272b`.
- [x] 249 tests still passing (no test changes needed — pure template/view context addition, no behavior change to existing fields).
- [x] Confirmed via direct production DB read (`railway connect Postgres --environment production`) that the previously-reported "sizes missing on dashboard" was not a code/data bug — the only active order at the time had `size` stored correctly and production was running the latest deployed code; likely a stale/uncached dashboard tab.

## PHASE 25e — Kotn Cup 26: per-patch placement (Left Arm / Right Arm) (DEPLOYED)

- [x] `KOTN_PATCH_PLACEMENTS` constant added (`left-arm`/`right-arm`) in `customer/views.py`; placement is chosen **per patch**, not per shirt — confirmed with the client since a 2-patch shirt needs one patch per arm.
- [x] Shirt builder (`pickup_join_kotn.html`): a `.placement-row` (Left Arm / Right Arm buttons) appears under a patch the moment it's selected. If the shirt has 2 patches, whichever arm is already taken by the other patch is disabled/greyed on this one — enforces one patch per arm without a separate error state. `isValid()` now also requires every selected patch to have a placement and rejects duplicate placements on the same shirt.
- [x] `_post_kotn` validation + storage updated: `shirts[].patches[]` now expects `{key, placement}` objects (was bare key strings); server validates each key and placement against the known lists and rejects duplicate placements per shirt. Stored patch dicts gained a `"placement"` field (display name, e.g. "Left Arm") alongside existing `name`/`crest`.
- [x] Placement shown everywhere patch names already appear: builder summary rows, phone-step order summary (`renderOrderSummary()`), both confirmation screen layouts (single- and multi-tag, `pickup_confirmation_kotn.html`), and the dashboard card (SSR block + JS `renderKotnEntry`, `dashboard/templates/dashboard/queue.html`). Legacy shirts stored before this change simply omit the placement text — no error, same pattern as the earlier Size rollout.
- [x] 251 tests passing (2 new: `test_invalid_placement_rejected`, `test_duplicate_placement_on_two_patches_rejected`; existing patch tests updated for the new `{key, placement}` POST shape).
- [x] Verified end-to-end in local browser preview: 2-patch shirt build with placement-taken greying, phone-step summary, submission, confirmation screen (both patches + placements), dashboard card (SSR and after live "Mark Ready" poll re-render). Commit `c359e1e`.
- [x] Fixed placement UX per user feedback: clicking an already-selected arm now deselects it (was previously stuck); clicking the arm already taken by the other patch on the shirt now swaps the two patches' placements instead of being disabled/blocked. Commit `4d59fd7`.

## PHASE 25f — Kotn Cup 26: ticker removal, missing sponsors, picked-up screen redesign, critical pickup-flow fix (DEPLOYED)

- [x] Removed the scrolling ticker footer entirely from the confirmation page (HTML, CSS/keyframes, preload hints, JS decode-gating logic) per explicit request. Commit `0007082`.
- [x] Added 2 sponsors that were missing from "With Thanks To": Rosie's Burgers (cropped/isolated from a multi-page `.ai` brand sheet via PyMuPDF — page 0 was the only transparent-background export; recolored from brand red to black for consistency with the rest of the monochrome grid) and NSS Sports (Press Partner). Grid moved from 3→4 columns to fit 8 logos across 2 even rows. Source files live in the untracked `Kotn Sponsors From Naya/` folder (not committed — same treatment as other raw design-asset folders this project). One file, `Tournament/slc-favicon.png` ("SL" mark), deliberately NOT added — it's a square favicon-style icon in a different category than the Drink/Food/Press Partner sponsor tiers; flagged to the user, unresolved as of this commit. Commit `14bc97d`.
- [x] Redesigned the picked-up ("done") confirmation screen from a bare one-line black-text message to match a client-provided mockup (`~/Downloads/Kotn Cup Confirmation Export.html`, a self-unpacking design-tool bundle — rendered via a temporary local HTTP server to extract exact fonts/colors/spacing): green قطن logo, "Thank You!" heading (Anton 30px), event-specific closing line, divider, the existing sponsor grid (retitled "With Thanks To Our Sponsors" to match the mockup), the `kotn-cup-toronto-badge.png` asset (previously removed from the ticker area in 25c, reused here), and a "Customize Another Shirt" button linking back to the join flow. The `cancelled` status path keeps the plainer maroon-logo treatment — no badge/CTA, since that's not something to celebrate. Commit `14bc97d`.
- [x] **Critical fix, found via real user testing**: the customer's phone never showed the picked-up screen in practice. Root cause was two leftover "shared kiosk device" behaviors that no longer make sense now that every customer uses their own phone: (1) `goReady()` had a 25s `setTimeout` that force-navigated the phone back to the join page regardless of whether staff had actually completed the handoff yet, and (2) `applyState()` called `clearInterval(pollInterval)` immediately upon reaching the ready state, so polling stopped and the phone could never detect a later `picked_up` transition even without the redirect. In a real event line, staff routinely take longer than 25s between marking an order Ready and physically handing it over and marking it Picked Up — so this was hit by default, not as an edge case. Removed the redirect, kept polling alive through the ready state, added a `reachedReady` guard so `goReady()`'s one-time DOM updates don't re-run on every subsequent poll tick. Verified locally by holding the ready state past the old 25s threshold (confirmed no redirect) then flipping the entry to `picked_up` mid-session (confirmed the phone still picked it up via poll). Commit `da7d8ce`.
- [x] 251 tests passing throughout (all four changes above were template/JS-only or asset additions — no model/view test surface changed).

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
