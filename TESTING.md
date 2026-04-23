# TESTING.md — Queue Light

---

## Running Tests

```bash
cd /Users/mansour/QueueLight
pytest
```

Run a single app:
```bash
pytest queue/tests/
pytest businesses/tests/
pytest dashboard/tests/
pytest customer/tests/
```

Run with verbose output:
```bash
pytest -v
```

Run with coverage:
```bash
pytest --cov=. --cov-report=term-missing
```

---

## Test Configuration

Tests use `pytest-django`. Config is in `pytest.ini`:
```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings
```

Database: tests use a real PostgreSQL test database (same DB engine as production). SQLite is not used — Queue Light does not require PostgreSQL-specific features (no range fields, no exclusion constraints), but using the same engine prevents surprises.

---

## Mocking Twilio

**Never make real Twilio API calls in tests.** Always mock `TwilioSMSBackend`.

Pattern:
```python
from unittest.mock import patch, MagicMock

@patch("notifications.sms.TwilioSMSBackend.send")
def test_call_next_sends_sms(mock_send, db, business, queue_entry):
    mock_send.return_value = True
    QueueService.call_next(business)
    mock_send.assert_called_once()
```

Alternatively, use the `SMSTestBackend` stub:
```python
from notifications.sms import SMSTestBackend
# swap in via Django settings override in conftest.py
```

---

## Fixtures

Shared fixtures live in `conftest.py` at project root.

| Fixture        | Returns                                | Notes                         |
|----------------|----------------------------------------|-------------------------------|
| `business`     | Business (batch mode, batch_size=5)    | Inactive by default           |
| `active_business` | Business (is_active=True)           |                               |
| `staff_phone`  | StaffPhone linked to active_business   |                               |
| `queue_entry`  | QueueEntry (status=WAITING)            | Linked to active_business     |
| `batch_entries`| 5 × QueueEntry in same batch           | For batch mode tests          |

---

## What to Test Per Phase

### Phase 3 — QueueService
- join() creates entry with correct position and batch_number
- join() rejects inactive business
- call_next() in batch mode: all entries in batch are marked CALLED
- call_next() in person mode: only lowest-position entry marked CALLED
- call_next() with empty queue raises RuleViolationError
- abandon() transitions WAITING → ABANDONED
- skip() transitions WAITING → SKIPPED
- skip() raises error in batch mode
- All invalid transitions raise RuleViolationError
- QueueEventLog row is written for every transition

### Phase 4 — SMS
- send() calls Twilio client with correct parameters
- send() returns False and logs SMS_FAILED when Twilio raises an exception
- call_next() completes even when SMS fails

### Phase 5 — Customer views
- GET /q/<slug>/ returns 200 with form
- POST /q/<slug>/ with valid data creates QueueEntry and redirects to confirmation
- POST /q/<slug>/ with inactive business returns 404
- GET /q/<slug>/confirmation/ returns batch number or position number

### Phase 6 — Staff dashboard
- GET /staff/<slug>/ redirects to login if no session
- POST /staff/<slug>/login/ with valid phone sets session and redirects to dashboard
- POST /staff/<slug>/login/ with unknown phone returns error
- GET /staff/<slug>/ with valid session returns queue list
- POST /staff/<slug>/next/ calls call_next() and redirects
- GET /api/queue/<slug>/status/ returns correct JSON

---

## Dev Server

```bash
cd /Users/mansour/QueueLight
python manage.py runserver
```

Customer join page: http://localhost:8000/q/<slug>/
Staff dashboard: http://localhost:8000/staff/<slug>/login/
Admin: http://localhost:8000/admin/

---

## Environment Setup

Copy `.env.example` to `.env` and fill in values:
```bash
cp .env.example .env
```

Required for tests:
- DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT
- TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN (can be fake values in test env)
- DJANGO_SECRET_KEY
