# AGENT.md — Queue Light

You are an autonomous engineer working on Queue Light, a minimal virtual queue system for Canadian retail businesses.

Follow: TASKS.md · ARCHITECTURE.md · TESTING.md · DEFINITION_OF_DONE.md · KNOWN_ISSUES.md

---

## What Queue Light Is

Customers scan a QR code, enter name + phone, get a batch or position number.
Staff see the queue on a dashboard and tap one button to call the next group.
Customers receive an SMS via Twilio when called.

Two modes per business: **batch** (groups of N) and **person** (one by one).

---

## Core Rules

- Never update QueueEventLog entries directly — they are immutable write-once audit records.
- Always use QueueService methods, never raw model `.save()` calls for state changes.
- Always run `python manage.py migrate` before running tests after any model change.
- Never hardcode secrets — all credentials come from environment variables.
- Never add business logic to views — use QueueService.
- The state machine lives in `queue/services.py`. The transition guard is the single source of truth. Do not bypass it.
- Staff authentication is phone-number-only + Django sessions. No JWT. No password.
- QueueEventLog is always written — even when SMS fails. SMS failure does not prevent the call from being logged.

---

## Workflow

1. **Before starting any task** — re-read TASKS.md and ARCHITECTURE.md. Do not proceed if prerequisites are incomplete.
2. **Implementation** — stay in scope. No speculative features.
3. **Test** — write tests before marking a task DONE. Run `pytest` for the affected app.
4. **Update docs** — update TASKS.md, ARCHITECTURE.md (if models/URLs changed), KNOWN_ISSUES.md (if edge cases found).
5. **Commit** — one commit per phase using the message format in TASKS.md.

---

## Permissions — What Requires Asking

**Never ask for permission for:**
- Editing any file in the repository
- Running Django management commands
- Running tests
- Starting or stopping the local dev server
- Creating new files and directories
- Non-destructive code changes

**Always pause and ask if:**
- A database schema change requires dropping existing data
- Something is genuinely unclear about product behaviour
- A destructive or irreversible action is required

---

## Testing

- Run `pytest` (all tests) before marking any phase complete.
- Twilio must always be mocked in tests — never make real API calls.
- Tests live in `{app}/tests/test_{feature}.py`.
- See TESTING.md for full instructions.

---

## Security

- Never hardcode secrets. Use `.env` + `python-dotenv`.
- Never expose QueueEventLog or phone numbers in public-facing API responses.
- Rate-limit the customer join endpoint: 20/hour per IP.
- Staff login is rate-limited: 10/minute.
- DEBUG=False in production.

---

## State Machine

Do not modify `ALLOWED_TRANSITIONS` in `queue/services.py` without updating ARCHITECTURE.md simultaneously.

---

## Git

- `git pull origin main` before starting any task.
- Never commit TASKS.md or KNOWN_ISSUES.md changes alone — always bundle with code changes in the same phase commit.
- Commit messages follow the format in TASKS.md.

---

## Stop Conditions

Stop and ask if:
- Schema change would drop data
- Twilio credentials or phone number configuration is unclear
- Business mode logic (batch vs person) produces ambiguous behaviour
- Something "works" but you haven't tried to break it yet

---

## Key Rule

If something works, try to break it before marking it done.
