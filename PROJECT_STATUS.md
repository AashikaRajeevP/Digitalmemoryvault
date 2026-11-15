# Digital Memory Vault - Project Status

Last updated: 2026-11-15

Repository: `AashikaRajeevP/memoryvault`  
Branch: `master`  
HEAD: `39628ab Fix strict CSRF validation on HTTPS`  
Remote status: `origin/master` is in sync with local HEAD (0 ahead, 0 behind)  
Working tree at inspection: clean. This `PROJECT_STATUS.md` file is newly created and is currently untracked until committed. Stage 2 migration wiring (changes to `app.py`, new `migrations/`, and `docs/STAGE2_DATABASE_PLAN.md`) is also uncommitted until committed.

## Status Legend

- **Implemented**: present in the code.
- **Tested locally**: covered by automated tests that pass locally.
- **Committed/pushed**: present in Git history and on `origin/master`.
- **Deployed/verified**: confirmed in the live Vercel environment. Items without this label are not confirmed in production.

## 1. Project Overview and Purpose

Digital Memory Vault is a Flask web application for preserving personal memories as a digital time capsule. Users create memories with a future open date. A memory remains locked until that date, with locked entries showing a countdown. Each user manages their own memories and can view total, locked, and unlocked counts.

The long-term goal is to extend the vault with photo attachments, voice memories, account email settings, password reset, and a redesigned frontend while preserving the existing Flask/Jinja/SQLAlchemy architecture.

## 2. Technology Stack and Architecture

### Stack

- Python 3.14.2
- Flask 3.1.3
- Jinja2 templates
- Flask-SQLAlchemy 3.1.1 / SQLAlchemy
- PostgreSQL via Neon in production
- SQLite locally when `DATABASE_URL` is blank
- Flask-Migrate 4.1.0 is wired in `app.py`; `migrations/` holds baseline revision `897fe5622bb6`
- Flask-WTF 1.3.0 for CSRF
- Flask-Limiter 4.1.1 with Redis support
- redis-py 8.1.0
- Werkzeug 3.1.8
- python-dotenv 1.2.4
- psycopg2-binary 2.9.13
- pytest 9.2.0 / pytest-flask 1.3.0 for tests
- Vercel for deployment

### Current architecture

- `app.py` creates the Flask app, loads configuration, initializes extensions, defines the `User` and `Memory` models inline, calls `db.create_all()`, and imports `routes.py`.
- `routes.py` contains all routes, auth helpers, validation, rate limits, and ownership checks.
- `services/security.py` contains password hash detection, hashing, and verification helpers.
- `templates/` contains Jinja templates: home, login, signup, create memory, my memories, memory detail, error, and base layout.
- `tests/` contains pytest configuration and security/behavior tests using a temporary SQLite database.
- `scripts/hash_existing_passwords.py` is a guarded dry-run/apply utility for converting legacy plaintext passwords to hashes.
- `migrate_to_postgres.py` is a SQLite-to-PostgreSQL copy utility. It is not part of the normal app runtime.
- `models.py` is currently commented out; models live in `app.py`.

### Important architecture caveats

- There is no application factory; `app` is a module-level Flask instance.
- Schema is owned by Alembic migrations in `migrations/`; the import-time `db.create_all()` call was removed.
- Flask-Migrate is wired via `Migrate(app, db)`. Baseline revision `897fe5622bb6` matches the current production schema and was validated on a disposable SQLite database (`upgrade`/`downgrade`/`db check`).
- See `docs/STAGE2_DATABASE_PLAN.md` for the incremental migration plan.
- The frontend is currently minimal HTML/Jinja only; there is no CSS/JS asset pipeline or GSAP integration yet.
- There is no `vercel.json` in the repository; Vercel configuration is external to the repo.

## 3. Existing Implemented Features

Implemented and locally tested:

- User signup with unique usernames and password hashing.
- User login with hashed passwords.
- Legacy plaintext password compatibility: a successful login automatically upgrades the stored plaintext password to a Werkzeug hash.
- User logout using a POST-only route.
- Create a memory with title, message, and open date.
- List the current user's memories.
- View a memory detail page.
- Date-based locking: locked memories hide their message until the open date.
- Locked-memory countdown in the memory list.
- Home dashboard with total, locked, and unlocked counts.
- Per-user memory ownership checks.
- Input validation for usernames, passwords, titles, messages, and open dates.
- Flash messages and a shared error page.
- Security headers and CSRF protection.
- Rate limiting for signup, login, and memory creation.
- Password conversion utility exists but has not been run against Neon.

Not yet implemented:

- Account email and account settings.
- Password reset.
- Photo or audio attachments.
- Frontend redesign and GSAP animations.
- Database migrations for future schema changes.

## 4. Stage 1 Security Changes

Stage 1 is **implemented, tested locally, committed, and pushed**. Production verification is still pending.

### Password hashing with legacy plaintext compatibility

- Signup stores `generate_password_hash(password)`.
- Login verifies legacy plaintext passwords with constant-time comparison when the stored value is not a hash.
- After a successful legacy login, the plaintext password is replaced with a hash and committed.
- Unknown usernames still perform a dummy password verification to reduce timing differences.
- Login failures use a generic message: `Invalid username or password.`
- `services/security.py` recognizes `scrypt:`, `pbkdf2:`, and `argon2:` hash prefixes.

### CSRF protection

- Flask-WTF `CSRFProtect` is enabled globally in `app.py`.
- All POST forms include a hidden `csrf_token`.
- The base template exposes a CSRF meta tag.
- CSRF failures return HTTP 400 through `handle_csrf_error`.
- No routes are exempted.
- `WTF_CSRF_SSL_STRICT` remains enabled; it is not disabled.
- Auth pages now use `Referrer-Policy: same-origin`, allowing same-origin form POSTs over HTTPS to satisfy Flask-WTF's strict referrer check while still avoiding cross-origin referrer leakage.
- The prior `no-referrer` policy caused production-only HTTP 400 responses on POST login/signup because Flask-WTF requires a same-origin `Referer` on secure requests.
- The fix is in commit `39628ab Fix strict CSRF validation on HTTPS`.

### Flask-Limiter and Upstash Redis

- `Flask-Limiter` is configured with `RATELIMIT_STORAGE_URI`.
- If the variable is blank or missing, the app falls back to `memory://`.
- On Vercel, using `memory://` logs a warning because rate limits would be per-instance rather than shared.
- HTTP/HTTPS REST URLs are rejected; the value must be a Redis URI such as `rediss://default:password@host:port`.
- Upstash Redis must use the Redis TLS URL, not the Upstash REST URL.
- `redis==8.1.0` is pinned.
- Current rate limits:
  - Signup: 5 per hour
  - Login: 10 per minute
  - Create memory: 60 per hour

### 12-character minimum password

- Default minimum is 12 characters in `app.py`.
- The configuration helper enforces a floor of 12 even if the environment value is lower.
- Maximum password length is 256 characters.
- `.env.example` documents `PASSWORD_MIN_LENGTH=12`.
- Existing legacy users with shorter passwords can still log in; the minimum applies to new signup passwords.

### Seven-day session lifetime

- `PERMANENT_SESSION_LIFETIME` is set to 7 days.
- Login sets `session.permanent = True`.
- Cookies use `HttpOnly` and `SameSite=Lax`.
- `SESSION_COOKIE_SECURE` is automatically true on Vercel or when explicitly enabled locally.
- `ProxyFix` handles Vercel forwarding headers for scheme, host, and client address.

### POST-only logout

- Logout is `POST /logout` only.
- The home page renders a CSRF-protected POST form for logout.
- GET `/logout` returns 405.

### Memory ownership checks

- Memory list and stats are filtered by the logged-in user's ID.
- Memory detail uses `mid` plus `user_id` and returns 404 for another user's memory.
- Protected routes redirect unauthenticated users to login.

### Additional Stage 1 protections

- Security headers: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, CSP, and HTML `Cache-Control: no-store`.
- HSTS is added on Vercel.
- Auth pages are marked `noindex, nofollow`.
- The development-only `/test` route was removed.
- CSRF error, 404, 413, and 500 handlers were added.

## 5. Current Deployment Status

### Vercel

- The project is deployed/reported as deployed on Vercel.
- The current HEAD `39628ab` is pushed to `origin/master`.
- Vercel deployment of that exact commit is **not verified from this session**.
- Production signup/login verification is still pending after the CSRF fix.

### Neon PostgreSQL

- Production database is reported as Neon PostgreSQL.
- Last read-only inspection/backup was performed on 2026-11-14.
- Neon database: `neondb`.
- Server version at inspection: PostgreSQL 18.7.
- The database was not modified during this status review.

### Upstash Redis

- The latest report says the Upstash Redis connection has been corrected.
- The application requires `RATELIMIT_STORAGE_URI` to be set to the Upstash Redis TLS URL.
- The value must be configured in Vercel environment variables for the relevant environments and requires a redeploy after changes.
- This configuration is not independently verifiable from the repository.

### Known deployment issues / pending checks

- The CSRF HTTPS 400 issue is fixed in code and covered by tests; production verification is pending.
- Signup is limited to 5 attempts per hour per client. Production signup testing may be blocked until the rate-limit window resets.
- Vercel must have a stable `SECRET_KEY`; changing it invalidates existing sessions and CSRF tokens.
- If `RATELIMIT_STORAGE_URI` is missing or set to `memory://`, rate limits are not shared across Vercel instances.
- `MAX_CONTENT_LENGTH` is currently 2 MB. It must be raised or made route-specific before implementing 10 MB photo uploads or 25 MB audio uploads.
- CSP currently allows same-origin scripts plus Cloudinary image/media/API domains. A third-party Cloudinary browser widget would require a CSP review.

## 6. Current Testing Status and Latest Results

Command:

```text
python -m pytest -q
```

Latest result:

```text
19 passed in 7.47s
```

Test coverage includes:

- Signup hashes passwords.
- Duplicate usernames are rejected.
- Minimum password length is 12.
- Public pages render.
- Authenticated pages render.
- Hashed-password login.
- Legacy plaintext login upgrade.
- Generic invalid-login errors.
- Memory detail requires login.
- Memory detail is owner-only.
- Invalid memory dates are rejected.
- Removed `/test` route returns 404.
- Security headers are present.
- Auth pages are noindex and use `same-origin` referrer policy.
- HTTPS login CSRF requires a same-origin referrer.
- HTTPS signup CSRF requires a same-origin referrer.
- Logout requires POST.
- Missing CSRF token is rejected.

Important testing caveats:

- Tests use a temporary SQLite database, not Neon.
- The general test fixture disables CSRF and rate limiting for ordinary behavior tests.
- The HTTPS CSRF regression tests explicitly enable CSRF and assert strict validation.
- No test currently accesses production Neon or Upstash.
- No test verifies the live Vercel deployment.

## 7. Database Status and Important Precautions

### Neon status at last inspection

Last verified: 2026-11-14 during read-only backup/inspection. This was not rechecked during the current review.

- Database: Neon `neondb`
- Tables: `users`, `memories`
- Users: 7 rows
- Memories: 6 rows
- `users` columns: `uid`, `username`, `password`
- No `email` column
- All 7 passwords were plaintext at inspection time
- No `alembic_version` table
- No password-reset-token table
- No photo/audio attachment tables
- No index on `memories.user_id`
- No duplicate usernames or orphan memories found at inspection
- Database size at backup time: approximately 7720 kB

### Verified backups

- Backup summary: `C:\Users\hp\AppData\Local\Temp\opencode\dmv-backups\BACKUP_SUMMARY.json`
- Neon backup directory: `C:\Users\hp\AppData\Local\Temp\opencode\dmv-backups\neon_20261114T150142Z`
- Local SQLite backup: `C:\Users\hp\AppData\Local\Temp\opencode\dmv-backups\sqlite_20261114T150142Z\memoryvault.db`
- Neon backup verification passed; restored row counts and checksums matched.
- Local SQLite backup integrity check passed.
- Local SQLite row counts at backup: 6 users, 5 memories.

Backups contain sensitive data, including plaintext passwords from the inspection time. Do not commit them, share them, or leave them in a public location.

### Precautions

- Back up Neon and verify the backup before any schema or data change.
- Do not run `migrate_to_postgres.py`, `scripts/hash_existing_passwords.py`, or any migration against Neon without explicit approval.
- The password conversion script is guarded by `--apply` and `--backup-confirmed`.
- Do not delete existing users.
- Do not run tests against Neon.
- Re-inspect production schema and counts before planning the next database change.
- The app currently uses `db.create_all()`; future schema changes need a deliberate migration plan.

## 8. Features Still to Implement

### Email and account settings

- Add an email column and account settings page.
- Allow legacy users to add or update their email.
- Decide and implement email verification behavior.

### Photo uploads through Cloudinary

- Add Cloudinary configuration and dependency.
- Add photo metadata and ownership model.
- Enforce planned limits: 10 MB per photo, 10 photos per memory.
- Choose a cover photo.
- Allow owners to preview locked-memory photos while hiding memory text.
- Ensure non-owners cannot access photos.

### Voice recording and playback

- Add browser recording and playback.
- Enforce planned limits: 25 MB and 10 minutes per audio memory.
- Keep audio inaccessible until the memory unlocks.
- `Permissions-Policy` already permits same-origin microphone use.
- CSP already permits same-origin/blob and Cloudinary media sources.

### Forgot/reset password using Resend

- Add Resend configuration and dependency.
- Add single-use, expiring reset tokens.
- Add `auth_version` or equivalent session invalidation.
- Add forgot-password and reset-password routes, templates, and rate limits.
- Avoid account enumeration in responses.
- Test token expiry, reuse prevention, and session invalidation.

### Frontend redesign with GSAP

- Redesign the current minimal templates.
- Add a same-origin CSS/JS asset structure.
- Add GSAP only after the backend flows are stable.
- Review CSP if any third-party scripts or styles are introduced.

### Database and migration work

- Flask-Migrate is now wired and `migrations/` is scaffolded with baseline revision `897fe5622bb6`.
- `db.create_all()` at import was removed; schema is owned by migrations. Local setup now requires `flask --app app db upgrade`.
- Next: stamp the existing Neon database as baseline `897fe5622bb6` (no DDL), then apply Stage 2 migrations one at a time per `docs/STAGE2_DATABASE_PLAN.md`.
- Back up Neon before any migration.
- Test migrations on a disposable database and show SQL before applying to Neon.

## 9. Important Decisions and Constraints

- Preserve Flask, Jinja, SQLAlchemy, and the existing architecture.
- Do not migrate the application to React.
- Do not delete existing users.
- Preserve existing memories and date-locking behavior.
- Keep the 12-character minimum password policy.
- Keep POST-only logout.
- Keep CSRF protection enabled; do not exempt auth routes.
- Keep `WTF_CSRF_SSL_STRICT` enabled.
- Keep ownership checks on every memory and future media operation.
- Use Cloudinary for photos/audio storage and Resend for password-reset email.
- Use Upstash Redis with a `rediss://` TLS URL for shared rate limiting on Vercel.
- Never commit `.env`, credentials, database files, or backups.
- Back up Neon before database changes.
- Never execute migrations or password conversion against Neon without explicit approval.
- Implement features incrementally and run the full test suite after each change.

## 10. Exact Next Steps

1. Confirm Vercel has deployed commit `39628ab`; check the deployment status and runtime logs.
2. Verify production signup after the 5-per-hour rate-limit window resets. Do not weaken the limit.
3. Verify production login and signup over HTTPS, confirming that POST requests no longer return 400.
4. Confirm auth responses send `Referrer-Policy: same-origin` and that session cookies are present.
5. The CSRF Referrer-Policy fix is already implemented, tested, committed, and pushed. Only production verification remains unless it still fails.
6. Confirm Vercel has `RATELIMIT_STORAGE_URI` set to the Upstash Redis TLS URL for the intended environments, then redeploy if it changed.
7. Confirm `SECRET_KEY` is stable across Vercel deployments and instances.
8. Commit and push this status document and any subsequent changes. Before this file was added, the tree was clean and `HEAD` was synced with `origin/master`.
9. The Stage 2 database plan is drafted in `docs/STAGE2_DATABASE_PLAN.md`. Flask-Migrate is wired with baseline revision `897fe5622bb6`, validated locally on a disposable SQLite database.
10. Before any Neon schema change, create and verify a fresh backup, prepare the migration, test it on a disposable database, and wait for explicit approval before applying it.
11. To adopt migrations on Neon, first stamp the existing database as baseline `897fe5622bb6` without running its DDL, then apply one Stage 2 migration at a time.
12. Resolve the deployment gap: decide how `flask db upgrade` runs for Vercel (manual release step or build hook) before the first production migration.

## Useful Local Commands

```powershell
pip install -r requirements-dev.txt
flask --app app db upgrade
python -m pytest -q
python app.py
```

After changing models, generate and review a migration before running the app:

```powershell
flask --app app db migrate -m "description"
flask --app app db upgrade
flask --app app db check
```

Do not run `scripts/hash_existing_passwords.py --apply` against Neon without explicit approval and verified backups.
