# Digital Memory Vault - Project Status

Last updated: 2026-11-15

- Repository: `AashikaRajeevP/memoryvault`
- Branch: `master`
- HEAD: `1d0207f Add email support and account settings`
- Remote status: local `HEAD` matches `origin/master` (`1d0207f`); it was not pushed from this session.
- Working tree at inspection: the Stage 3 FIX (signup email verification + login-by-email redesign) is uncommitted. Modified: `app.py`, `routes.py`, `templates/login.html`, `tests/conftest.py`, `tests/test_accounts.py`, `tests/test_security.py`, `.env.example`, `requirements.txt`, `PROJECT_STATUS.md`, `docs/STAGE2_DATABASE_PLAN.md`; new: `services/otp.py`, `services/email.py`, `templates/verify.html`, `migrations/versions/fc35b4ffa9c0_email_verification.py`, `tests/test_signup_verification.py`, `tests/test_email_service.py`. Not committed, not pushed, not deployed.

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
- Flask-Migrate 4.1.0 is wired in `app.py`; `migrations/` holds baseline `897fe5622bb6`, email revision `6694a1a15bcb`, and email-verification revision `fc35b4ffa9c0`
- Flask-WTF 1.3.0 for CSRF
- Flask-Limiter 4.1.1 with Redis support
- redis-py 8.1.0
- resend 2.21.0 for signup verification email
- Werkzeug 3.1.8
- python-dotenv 1.2.4
- psycopg2-binary 2.9.13
- pytest 9.2.0 / pytest-flask 1.3.0 for tests
- Vercel for deployment

### Current architecture

- `app.py` creates the Flask app, loads configuration, initializes extensions (including Flask-Migrate), defines the `User`, `EmailVerification`, and `Memory` models inline, and imports `routes.py`. Schema is created by migrations, not at import.
- `routes.py` contains all routes, auth helpers, validation, rate limits, and ownership checks.
- `services/security.py` contains password hash detection, hashing, and verification helpers.
- `services/accounts.py` contains email normalization and validation helpers.
- `services/otp.py` contains OTP generation and HMAC-SHA256 hashing/verification helpers.
- `services/email.py` contains the Resend OTP email sender (lazy import; no-op when delivery is disabled or under test).
- `templates/` contains Jinja templates: home, login, signup, account settings, create memory, my memories, memory detail, error, and base layout.
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

- Two-step signup: collect username, email, and password, then verify a 6-digit code emailed via Resend before the account is created.
- Email verification OTP: single-use, 5-minute expiry, HMAC-SHA256 hashed (never stored or logged in plaintext), attempt-limited, resend cooldown, session-bound, and previous codes invalidated on resend.
- User login by email with hashed passwords; unverified accounts cannot log in.
- Required email on user accounts with format validation, normalization, and uniqueness.
- Account settings page (`/account`) for logged-in users to update their own email.
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

- Password reset (forgot/reset flow).
- Photo or audio attachments.
- Frontend redesign and GSAP animations.
- Applying schema migrations to production Neon.

## 4. Stage 1 Security Changes

Stage 1 is **implemented, tested locally, committed, and pushed**. Production verification is still pending.

### Password hashing with legacy plaintext compatibility

- Signup stores `generate_password_hash(password)`.
- Login verifies legacy plaintext passwords with constant-time comparison when the stored value is not a hash.
- After a successful legacy login, the plaintext password is replaced with a hash and committed.
- Unknown usernames still perform a dummy password verification to reduce timing differences.
- Login failures use a generic message. It was `Invalid username or password.` in Stage 1 and is now `Invalid email or password.` after the Stage 3 FIX login-by-email redesign.
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

## 5. Stage 3 Email, Account Settings, and Signup Verification

Stage 3 FIX is **implemented and tested locally**. It is **not committed**, and the database **has not been migrated in production**.

### Email field

- `User.email` is a required (`NOT NULL`) `String` column; it was added by migration `6694a1a15bcb` and made `NOT NULL` by migration `fc35b4ffa9c0`.
- Uniqueness is enforced with a unique index `ix_users_email` (not a column-level constraint) so the migration works on both SQLite and PostgreSQL.
- Email is normalized (trimmed and lowercased) before storage and comparison.
- Format is validated in `services/accounts.py` (`normalize_email`, `is_valid_email`, max length 254).

### Signup (two-step with OTP)

- `GET/POST /signup` validates username, password, and email, then creates a pending `EmailVerification` row. No `User` row is created yet.
- A 6-digit code is emailed via Resend and the pending challenge token is stored in the session (`pending_signup_token`).
- `POST /signup/verify` verifies the code, re-checks username/email uniqueness, then creates the `User` with `email_verified=True`.
- After successful verification the user is **not** logged in; they are redirected to `/login` (decision 3).
- `POST /signup/resend` issues a new code subject to a cooldown; the previous code is invalidated.
- Duplicate emails that belong to an already-registered user are rejected; a pending (unverified) signup for the same email is replaced as a retry.

### OTP security

- Codes are generated with `secrets.randbelow` and stored only as an HMAC-SHA256 digest (`services/otp.py`) keyed by `OTP_SECRET`, bound to the challenge token. Plaintext codes are never stored, logged, or returned.
- Single-use: a challenge is marked `used` on success and on attempt-limit breach.
- Expiry: `OTP_TTL_SECONDS` (default 300). Expired challenges are rejected and purged.
- Attempt limit: `OTP_MAX_ATTEMPTS` (default 5); breaching it invalidates the challenge.
- Resend cooldown: `OTP_RESEND_COOLDOWN_SECONDS` (default 60); a resend regenerates the code, resets attempts, and invalidates the prior code.
- Session binding: verification requires the matching `pending_signup_token` in the session.
- Cleanup: used or expired challenges are deleted on the next signup (`_purge_expired_verifications`).
- `OTP_SECRET` falls back to `SECRET_KEY` when unset, but a dedicated value is recommended.

### Login

- Login is by **email** (not username) plus password.
- Unknown email, wrong password, and unverified account all return the same generic error (`Invalid email or password.`) with HTTP 401.
- Unknown emails still perform a dummy password verification to reduce timing differences.
- Legacy plaintext passwords are upgraded to a hash on successful login.
- Login never sends an OTP.

### Account settings

- `GET /account` and `POST /account`, protected by `login_required`, let the user update their own email.
- The route only reads/writes the row for `session['user_id']`; there is no user id parameter, so a user cannot target another account.
- Duplicate emails are rejected, excluding the user's own current email.

### CSRF and security

- All forms include a hidden `csrf_token`; the global `CSRFProtect` enforces it.
- `signup_verify` and `signup_resend` were added to `AUTH_ENDPOINTS`, so those pages are `noindex, nofollow` and send `Referrer-Policy: same-origin`.
- Existing authentication, password hashing, session lifetime, and memory behavior are unchanged.

### Migration

- Revision: `fc35b4ffa9c0` (`email verification`), down revision `6694a1a15bcb` (additive; history preserved).
- Adds the `email_verifications` table, adds `users.email_verified` (`NOT NULL DEFAULT false`), and alters `users.email` to `NOT NULL`.
- Validated on a disposable SQLite database: `flask db upgrade` applies cleanly, `flask db check` reports no drift, and the `ix_users_email` unique index survives the batch table rebuild.
- Not applied to Neon.

## 6. Current Deployment Status

### Vercel

- The project is deployed/reported as deployed on Vercel.
- The current HEAD `1d0207f` matches `origin/master`; the Stage 3 FIX working-tree changes are not committed or pushed.
- Vercel deployment of the Stage 3 FIX is **not verified from this session**.
- Production signup/login verification is still pending; production is currently broken because `users.email` does not exist in Neon (see section 8).

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

## 7. Current Testing Status and Latest Results

Command:

```text
python -m pytest -q
```

Latest result:

```text
63 passed
```

Test coverage includes:

- Resend email service: no-op when disabled or under test; sends the expected payload when enabled; returns `False` and does not log the OTP on provider failure.

- Signup creates a pending challenge, not a user.
- Signup does not authenticate before verification.
- The OTP is 6 digits and is not exposed in the response or logged.
- Only the HMAC-SHA256 digest is stored (verified against `OTP_SECRET` + token).
- Verification success creates a verified user and redirects to login without authenticating.
- Verification failure increments attempts; breaching the limit invalidates the challenge.
- Expired codes are rejected; codes are single-use.
- Verification requires a pending session token and rejects unknown challenges.
- Verification requires CSRF.
- Resend requires a pending session, enforces the cooldown, resets attempts, and invalidates the previous code.
- Email-send failure marks the challenge used for both signup and resend.
- Expired challenges are purged on the next signup.
- Login does not send an OTP.
- Signup hashes passwords.
- Signup stores a normalized email.
- Signup requires a valid email and rejects invalid formats.
- Registered duplicate emails are rejected (case-insensitively).
- Verified users can log in by email; unverified users cannot.
- Account settings requires login.
- Account settings shows and updates the current user's email.
- Account updates reject invalid and duplicate emails.
- A user cannot modify another user's account.
- Account updates require a CSRF token.
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

## 8. Database Status and Important Precautions

### Neon status at last inspection

Last verified: 2026-11-14 during read-only backup/inspection. This was not rechecked during the current review.

- Database: Neon `neondb`
- Tables: `users`, `memories`
- Users: 7 rows
- Memories: 6 rows
- `users` columns: `uid`, `username`, `password`
- No `email` column in production; the code now defines `email` (NOT NULL) via migrations `6694a1a15bcb` and `fc35b4ffa9c0`, which are not yet applied to Neon. This mismatch is why production signup/login currently return HTTP 500.
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
- The app now uses Alembic migrations (`migrations/`); the import-time `db.create_all()` was removed.
- Migration `6694a1a15bcb` (email) and `fc35b4ffa9c0` (email verification) must not be applied to Neon until the baseline is stamped and a fresh backup is verified.
- The agreed production plan (pending separate approval) is to discard the existing Neon data after a verified backup, then run the full migration chain from scratch (see section 12). Do not delete production data or run migrations against Neon without explicit approval.
- Production database status: not migrated. Neon still has no `alembic_version` table, no `email` column, and no `ix_users_email` index.

## 9. Features Still to Implement

### Email and account settings

- Implemented: required email column, two-step signup with email OTP verification, login by email, and the `/account` settings page (Stage 3, migrations `6694a1a15bcb` and `fc35b4ffa9c0`).
- Remaining: apply the migrations to production after a verified backup and reset (see section 8 and `docs/STAGE2_DATABASE_PLAN.md`).

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
- Email migration `6694a1a15bcb` (adds `users.email` + unique index `ix_users_email`) and email-verification migration `fc35b4ffa9c0` (adds `email_verifications`, `users.email_verified`, and `NOT NULL` on `users.email`) are implemented and validated locally but not applied.
- `db.create_all()` at import was removed; schema is owned by migrations. Local setup now requires `flask --app app db upgrade`.
- Because production data is disposable (approved), the agreed path is to reset Neon and run the full chain rather than stamp the legacy schema (see section 12).
- Back up Neon before any migration.
- Test migrations on a disposable database and show SQL before applying to Neon.

## 10. Important Decisions and Constraints

- Preserve Flask, Jinja, SQLAlchemy, and the existing architecture.
- Do not migrate the application to React.
- Do not delete existing users.
- Preserve existing memories and date-locking behavior.
- Keep the 12-character minimum password policy.
- Keep POST-only logout.
- Keep CSRF protection enabled; do not exempt auth routes.
- Keep `WTF_CSRF_SSL_STRICT` enabled.
- Keep ownership checks on every memory and future media operation.
- Use Cloudinary for photos/audio storage and Resend for signup verification and password-reset email.
- Use Upstash Redis with a `rediss://` TLS URL for shared rate limiting on Vercel.
- Never commit `.env`, credentials, database files, or backups.
- Back up Neon before database changes.
- Never execute migrations or password conversion against Neon without explicit approval.
- Implement features incrementally and run the full test suite after each change.

## 11. Exact Next Steps

1. Review the Stage 3 FIX working-tree changes, then commit and push when approved (not done in this session).
2. Set Vercel environment variables: `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `RESEND_ENABLED=true`, and a dedicated `OTP_SECRET` (see section 12).
3. Verify a Resend sending domain for production; `onboarding@resend.dev` is testing-only (see section 12).
4. Create a fresh Neon backup and verify it by restoring into a separate disposable PostgreSQL database, not just `pg_restore --list` (see section 12).
5. Review the production reset/deployment plan in section 12 and grant explicit approval before running anything against Neon.
6. After the reset migration, verify production signup (two-step OTP) and login over HTTPS.
7. Verify the 6-digit code email arrives from the verified sender domain.
8. Confirm auth responses send `Referrer-Policy: same-origin` and that session cookies are present.
9. Confirm Vercel has `RATELIMIT_STORAGE_URI` set to the Upstash Redis TLS URL, then redeploy if it changed.
10. Confirm `SECRET_KEY` and `OTP_SECRET` are stable across Vercel deployments and instances.

## 12. Production Reset and Deployment Plan (awaiting separate approval)

The existing Neon data is disposable (approved). The plan is to back it up, verify the backup by restoring it into a separate disposable PostgreSQL database, then drop ONLY the four application objects and rebuild the schema from scratch with the full migration chain, then deploy the Stage 3 FIX code.

> DESTRUCTIVE: Step 3 permanently deletes all `users`, `memories`, `email_verifications`, and migration history. It must run ONLY after Step 2 has produced a backup that has been successfully restored and verified. Do NOT run any step against Neon without explicit approval.

### Step 1 - Back up Neon (read-only)

```powershell
pg_dump "$env:PRODUCTION_DATABASE_URL" --format=custom --file "C:\Users\hp\AppData\Local\Temp\opencode\dmv-backups\neon_pre_stage3.dump"
```

### Step 2 - Verify the backup by restoring it into a SEPARATE disposable PostgreSQL

`pg_restore --list` only lists the archive contents; it does NOT prove the dump restores. Always restore into a throwaway PostgreSQL database (never Neon) and compare counts.

```powershell
# Point these at a disposable local/scratch Postgres, NEVER Neon.
$local = "-h 127.0.0.1 -p 5432 -U postgres"
createdb $local dmv_restore_check
pg_restore $local --no-owner --dbname=dmv_restore_check "C:\Users\hp\AppData\Local\Temp\opencode\dmv-backups\neon_pre_stage3.dump"

# Compare against the pre-reset production inspection.
psql $local -d dmv_restore_check -c "select (select count(*) from users) as users, (select count(*) from memories) as memories;"
psql $local -d dmv_restore_check -c "select username, email from users order by uid;"
```

The restore must complete without errors and the row counts must match production. Keep the dump until the reset and upgrade are confirmed healthy. This exact dump -> restore -> verify procedure was validated locally against a disposable PostgreSQL 16.4 instance.

### Step 3 - Targeted reset of ONLY the application objects (destructive)

Drop only the four application objects. Do NOT use `DROP SCHEMA public CASCADE`, which would also remove the `public` schema itself, its grants/ownership, and any extensions or objects Neon manages.

```powershell
psql "$env:PRODUCTION_DATABASE_URL" -c "DROP TABLE IF EXISTS email_verifications CASCADE; DROP TABLE IF EXISTS memories CASCADE; DROP TABLE IF EXISTS users CASCADE; DROP TABLE IF EXISTS alembic_version CASCADE;"
```

Order matters: `memories` is dropped before `users` because `memories.user_id` references `users.uid`. `alembic_version` is dropped so the migration chain starts from base.

### Step 4 - Apply the full migration chain

```powershell
$env:DATABASE_URL = $env:PRODUCTION_DATABASE_URL
$env:SECRET_KEY = $env:PRODUCTION_SECRET_KEY
flask --app app db upgrade
flask --app app db current
flask --app app db check
```

Expected chain: `897fe5622bb6` (initial) -> `6694a1a15bcb` (add users email) -> `fc35b4ffa9c0` (email verification, head).

### Step 5 - Deploy the application code

```powershell
git add -A
git commit -m "Add signup email verification and email login"
git push origin master
```

Vercel has no build hook for migrations, so `flask db upgrade` (step 4) must run as a manual release step BEFORE the new code is served. Because the app now selects `users.email`, deploying code before the migration reproduces the current 500 errors.

### Step 6 - Verify

- `POST /signup` creates a pending challenge and sends a code (no `User` row yet).
- `POST /signup/verify` with the correct code creates a verified user and redirects to `/login`.
- `POST /login` succeeds with email + password and no OTP.
- Neon shows tables `users`, `memories`, `email_verifications`, and `alembic_version` at `fc35b4ffa9c0`.

### Migration chain validated on fresh PostgreSQL (not only SQLite)

On 2026-11-15 the full chain was run against a fresh, disposable PostgreSQL 16.4 database:

- `flask db upgrade` -> `fc35b4ffa9c0` (head); `flask db check` -> no new operations.
- `flask db downgrade base` then `flask db upgrade` again -> head, cleanly.
- Tables: `alembic_version`, `email_verifications`, `memories`, `users`.
- `users`: `email varchar NOT NULL`, `email_verified boolean NOT NULL DEFAULT false`, unique `ix_users_email`, unique `users_username_key`.
- `email_verifications`: 11 `NOT NULL` columns; unique `email_verifications_token_key`; `ix_email_verifications_email`.
- A `pg_dump` -> `pg_restore` into a separate disposable database restored all rows and the revision `fc35b4ffa9c0`.

### Required production environment variables (Vercel)

- `RESEND_API_KEY` - Resend API key.
- `RESEND_FROM_EMAIL` - sender address on a verified domain (see below).
- `RESEND_ENABLED=true` - must be exactly `true` (or `1`/`yes`) for delivery; otherwise the app silently skips sending and signup cannot be completed.
- `OTP_SECRET` - a dedicated random secret (for example `python -c "import secrets; print(secrets.token_urlsafe(48))"`). Falls back to `SECRET_KEY` when unset, but a dedicated value is required for production.
- Existing: `SECRET_KEY`, `DATABASE_URL`, `RATELIMIT_STORAGE_URI`; `SESSION_COOKIE_SECURE` is automatic on Vercel.

### Resend sender domain requirements (production)

- `onboarding@resend.dev` is a shared testing sender that Resend only delivers to the account owner's own email address. It cannot send to arbitrary users.
- Production requires a domain verified in Resend: add the domain, publish the required DNS records (SPF/DKIM, and DMARC as recommended), wait for verification, then set `RESEND_FROM_EMAIL` to an address on that verified domain (for example `no-reply@yourdomain.com`).
- Until the domain is verified, `POST /signup` can create a pending challenge but the code will not be delivered to real users.

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
