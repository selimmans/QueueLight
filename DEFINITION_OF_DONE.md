# DEFINITION_OF_DONE.md — Queue Light

A feature is **not done** until all of the following are true.

---

## Universal Checklist (every task)

- [ ] Code is written and works
- [ ] At least one test covers the happy path
- [ ] At least one test covers the primary error path
- [ ] Error handling is clean — no unhandled exceptions reach the user
- [ ] QueueEventLog is written wherever a state change occurs
- [ ] TASKS.md is updated
- [ ] Relevant doc (ARCHITECTURE.md, KNOWN_ISSUES.md) is updated if needed

---

## Per-Component Criteria

### Business model
- [ ] slug is unique and URL-safe
- [ ] Inactive business is rejected at join time
- [ ] Admin can create/edit/deactivate businesses

### StaffPhone
- [ ] Unique per business (phone + business combo)
- [ ] Phone number stored in E.164 format

### QueueEntry
- [ ] Position is sequential within the business, not globally unique
- [ ] batch_number is null in person mode
- [ ] joined_at is set automatically
- [ ] called_at is set only on transition to CALLED

### QueueEventLog
- [ ] Rows are never updated, only inserted
- [ ] Every state transition writes a log row
- [ ] SMS outcome (sent/failed) is logged separately from the CALLED event
- [ ] meta field includes mode and batch_size

### QueueService
- [ ] All transitions go through the guard — no raw .save() calls elsewhere
- [ ] call_next() is atomic (transaction.atomic + select_for_update)
- [ ] call_next() does not fail if SMS fails
- [ ] join() rejects inactive businesses
- [ ] skip() raises error in batch mode

### TwilioSMSBackend
- [ ] Never raises exceptions to the caller — returns bool
- [ ] Logs SMS_FAILED to QueueEventLog on failure
- [ ] Mocked in all tests (no real API calls ever)

### Customer join page
- [ ] Renders correctly on a 375px-wide mobile screen
- [ ] Shows business name and logo colour
- [ ] Confirmation page clearly shows batch number (batch mode) or position (person mode)
- [ ] Works without JavaScript (form is native HTML POST)

### Staff dashboard
- [ ] Redirects to login if no valid session
- [ ] Phone-number login works for registered StaffPhone entries
- [ ] Queue list shows all WAITING entries
- [ ] "Next" button calls call_next() and refreshes the view
- [ ] Last called batch/person shown at top
- [ ] 5-second polling updates queue without full page reload
- [ ] Works on a mobile screen

### QR code
- [ ] QR code PNG is valid and scannable
- [ ] Points to correct /q/<slug>/ URL
- [ ] Downloadable from staff dashboard

### Health check
- [ ] GET /health/ returns 200 {"status": "ok"} when DB is up
- [ ] GET /health/ returns 503 {"status": "degraded"} when DB is down
- [ ] No auth required
