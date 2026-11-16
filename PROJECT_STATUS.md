# Digital Memory Vault - Project Status

Last updated: 2026-11-16

- Repository: `AashikaRajeevP/memoryvault`
- Branch: `master`
- HEAD: `d9ec607 Simplify signup to email and password only`
- Remote status: local `HEAD` is ahead of `origin/master` (`112a1b2`).
- Working tree at inspection: signup is email/password only with immediate account creation, a Forgot Password flow using email OTP is implemented, and the Photo Attachments feature is implemented end-to-end. Modified/added: `app.py`, `routes.py`, `services/photos.py`, `services/otp.py`, `static/create_memory.js`, `static/styles.css`, `templates/base.html`, `templates/create_memory.html`, `templates/memory_detail.html`, `templates/my_memories.html`, `migrations/versions/7c1a9e4b2f60_password_reset.py`, `migrations/versions/a3f9c1d7e2b4_memory_photos.py`, `tests/conftest.py`, `tests/test_accounts.py`, `tests/test_security.py`, `tests/test_password_reset.py`, `tests/test_photos.py`, `.env.example`, and this document. New migrations `7c1a9e4b2f60` and `a3f9c1d7e2b4` are validated locally but **not applied to Neon**. Not committed, not pushed, not deployed.

## Status Legend

- **Implemented**: present in the code.
- **Tested locally**: covered by automated tests that pass locally.
- **Committed/pushed**: present in Git history and on `origin/master`.
- **Deployed/verified**: confirmed in the live Vercel environment. Items without this label are not confirmed in production.

## 1. Project Overview and Purpose

Digital Memory Vault is a Flask web application for preserving personal memories as a digital time capsule. Users create memories with a future open date. A memory remains locked until that date, with locked entries showing a countdown. Each user manages their own memories and can view total, locked, and unlocked counts.

The long-term goal is to extend the vault with photo attachments, voice memories, password reset, and a redesigned frontend while preserving the existing Flask/Jinja/SQLAlchemy architecture.

## 2. Technology Stack and Architecture

### Stack

- Python 3.14.2
- Flask 3.1.3
- Jinja2 templates
- Flask-SQLAlchemy 3.1.1 / SQLAlchemy
- PostgreSQL via Neon in production
- SQLite locally when `DATABASE_URL` is blank
- Flask-Migrate 4.1.0 is wired in `app.py`; `migrations/` holds baseline `897fe5622bb6`, email revision `6694a1a15bcb`, email-verification revision `fc35b4ffa9c0`, password-reset/auth-version revision `7c1a9e4b2f60`, and memory-photos revision `a3f9c1d7e2b4` (head)
- Cloudinary direct browser uploads via HMAC-SHA1 signatures (no binary uploads through server)
- Flask-WTF 1.3.0 for CSRF
- Flask-Limiter 4.1.1 with Redis support
- redis-py 8.1.0
- resend 2.21.0 for verification and password-reset email
- Werkzeug 3.1.8
- python-dotenv 1.2.4
- psycopg2-binary 2.9.13
- pytest 9.2.0 / pytest-flask 1.3.0 for tests
- Vercel for deployment

### Current architecture

- `app.py` creates the Flask app, loads configuration, initializes extensions (including Flask-Migrate), defines the `User`, `EmailVerification` (legacy, unused), `PasswordReset`, `Memory`, and `MemoryPhoto` models inline, and imports `routes.py`. Schema is created by migrations, not at import.
- `routes.py` contains all routes, auth helpers, validation, rate limits, ownership checks, and photo management endpoints.
- `services/photos.py` contains Cloudinary signing, photo payload validation, user folder scoping, and asset deletion helpers.
- `services/security.py` contains password hash detection, hashing, and verification helpers.
- `services/accounts.py` contains email normalization and validation helpers.
- `services/otp.py` contains OTP generation and HMAC-SHA256 hashing/verification helpers.
- `services/email.py` contains the Resend OTP email sender (lazy import; no-op when delivery is disabled or under test).
- `static/` contains `create_memory.js` (client-side image selection, previewing, progress tracking, and direct Cloudinary uploads) and `styles.css` (responsive layout, memory cards, photo previews, badges, and responsive photo gallery).
- `templates/` contains Jinja templates: home, login, signup, forgot password, reset password, create memory, my memories, memory detail, error, and base layout.
- `tests/` contains pytest configuration and security/behavior tests using a temporary SQLite database (`test_photos.py` covers Cloudinary signing, photo validation, access control, locked/unlocked views, and deletions).
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

- Signup with email and password only: the account is created immediately (unverified), then the user is redirected to login. No email is sent at signup. The legacy `username` column is filled with a generated internal value (`user:<normalized_email>`, with a numeric suffix if needed) and is not shown to the user.
- Forgot Password flow: request a 6-digit OTP by email, verify it, and set a new password. Uses the same OTP utilities as before.
- Password-reset OTP security: single-use, 5-minute expiry, HMAC-SHA256 hashed (never stored or logged in plaintext), attempt-limited, resend cooldown, session-bound, and previous codes invalidated on resend and on successful reset.
- User login by email with hashed passwords; `email_verified` is stored but no longer gates login (new signups are unverified and can log in immediately).
- Existing sessions are invalidated after a password reset via `users.auth_version`.
- Required email on user accounts with format validation, normalization, and uniqueness.
- Legacy plaintext password compatibility: a successful login automatically upgrades the stored plaintext password to a Werkzeug hash.
- User logout using a POST-only route.
- Create a memory with title, message, open date, and optional photo attachments (one cover photo and multiple additional photos).
- Photo attachments with direct browser-to-Cloudinary signed uploads: credentials stay secure on the server, image binaries never traverse the Flask app, and assets are isolated in per-user Cloudinary folders (`memoryvault/users/<user_id>/...`).
- Cover photo support: one photo designated as the cover photo; displayed prominently on memory cards and detail pages even while the memory is locked.
- Additional photos privacy: additional photos and their metadata are strictly withheld by the backend while the memory is locked (`photos = []`). Once unlocked, additional photos are displayed in a responsive grid gallery with full-resolution viewing.
- Client-side upload UX: file type and size validation, instant client previews, radio button cover photo selector, remove buttons, upload progress indicators, submit button lock during uploads, and error notifications.
- Memory & photo cleanup: deleting a memory cascades to delete `MemoryPhoto` database records and automatically destroys associated Cloudinary assets via Cloudinary's Destroy API; failed creation or DB errors clean up in-flight user uploads to prevent orphaned assets.
- Graceful degradation: if Cloudinary is unconfigured, users can still create and manage text-only memories cleanly with informational feedback.
- List the current user's memories with cover photo thumbnails.
- View a memory detail page with cover photo, countdown if locked, and message/photo gallery if unlocked.
- Date-based locking: locked memories hide their message and additional photos until the open date.
- Locked-memory countdown in the memory list.
- Home dashboard with total, locked, and unlocked counts.
- Per-user memory ownership checks.
- Input validation for emails, passwords, titles, messages, open dates, photo formats, photo sizes, and photo counts.
- Flash messages and a shared error page.
- Security headers (including Cloudinary in CSP `img-src`, `connect-src`, and `media-src`) and CSRF protection.
- Rate limiting for signup, login, memory creation, and upload signature requests (120/hr).
- Password conversion utility exists but has not been run against Neon.

Not yet implemented:

- Audio / voice attachments.
- Frontend redesign and GSAP animations.
- Applying schema migrations (`7c1a9e4b2f60` and `a3f9c1d7e2b4`) to production Neon.

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
  - Forgot password: 5 per hour
  - Reset password (submit): 10 per hour
  - Reset code resend: 5 per hour

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

## 5. Stage 3 Email and Signup Verification

Stage 3 FIX is **implemented, tested locally, committed, and pushed**. Signup was then simplified to email and password only, and a Forgot Password flow was added; those follow-ups are **implemented and tested locally** but not yet committed. See sections 8 and 12 for production database status.

### Email field

- `User.email` is a required (`NOT NULL`) `String` column; it was added by migration `6694a1a15bcb` and made `NOT NULL` by migration `fc35b4ffa9c0`.
- Uniqueness is enforced with a unique index `ix_users_email` (not a column-level constraint) so the migration works on both SQLite and PostgreSQL.
- Email is normalized (trimmed and lowercased) before storage and comparison.
- Format is validated in `services/accounts.py` (`normalize_email`, `is_valid_email`, max length 254).

### Signup (email and password only)

- `GET/POST /signup` validates password and email, then creates the `User` immediately with `email_verified=False`. No email is sent at signup.
- The signup page collects **email and password only**. No username is shown or accepted from the user.
- The legacy `users.username` column remains `NOT NULL UNIQUE` (the schema is unchanged). New accounts receive an internal generated username: `user:<normalized_email>`. If that value already belongs to an old account, a numeric suffix (`-2`, `-3`, ...) is added until it is free.
- Internal username collisions are retried with the next free suffix; a duplicate email registered in the meantime is rejected.
- After successful signup the user is **not** logged in; they are redirected to `/login`.
- Registered duplicate emails are rejected. The former two-step challenge routes (`/signup/verify`, `/signup/resend`) and `templates/verify.html` were removed. The `EmailVerification` model/table is retained as legacy/unused and is not dropped.
- `email_verified` is stored but no longer gates login, so an account created by the immediate signup can log in right away.

### Forgot Password (email OTP)

- `GET/POST /forgot_password` accepts a registered email and always responds with the same message: "If an account exists for that email, we've sent a password reset code." This avoids account enumeration.
- A `PasswordReset` challenge is created for every syntactically valid email; an email is sent only when a matching account exists.
- `GET/POST /reset_password` verifies the 6-digit OTP and sets a new password. The form also requires `confirm_password`.
- Passwords are validated (length and confirmation) before OTP verification, so a valid OTP cannot be probed with an invalid password submission.
- A successful reset hashes the new password with the existing Werkzeug method, increments `users.auth_version`, clears the session, and redirects to `/login`.
- `POST /reset_password/resend` issues a new code subject to a cooldown; the previous code is invalidated and attempts are reset.
- Both known and unknown emails are session-bound through `pending_reset_token`; unknown-email challenges can never produce a password change.
- Rate limits: forgot password 5/hour, reset submit 10/hour, resend 5/hour.
- `send_otp_email` is reused unchanged; the Resend dependency and configuration remain in place.

### OTP security

- Codes are generated with `secrets.randbelow` and stored only as an HMAC-SHA256 digest (`services/otp.py`) keyed by `OTP_SECRET`, bound to the challenge token. Plaintext codes are never stored, logged, or returned.
- `services/otp.py` also provides `hash_token`, used to store only the HMAC-SHA256 digest of reset challenge tokens.
- Single-use: a challenge is marked `used` on success and on attempt-limit breach. Reset consumption uses a guarded `UPDATE ... WHERE used = false` so concurrent submissions cannot both succeed.
- Expiry: `OTP_TTL_SECONDS` (default 300). Expired challenges are rejected and purged.
- Attempt limit: `OTP_MAX_ATTEMPTS` (default 5); breaching it invalidates the challenge.
- Resend cooldown: `OTP_RESEND_COOLDOWN_SECONDS` (default 60); a resend regenerates the code, resets attempts, and invalidates the prior code.
- Session binding: reset verification requires the matching `pending_reset_token` in the session.
- Cleanup: used or expired reset challenges are deleted on the next forgot-password request (`_purge_expired_resets`).
- `OTP_SECRET` falls back to `SECRET_KEY` when unset, but a dedicated value is recommended.

### Login and session invalidation

- Login is by **email** (not username) plus password.
- Unknown email and wrong password return the same generic error (`Invalid email or password.`) with HTTP 401.
- Unknown emails still perform a dummy password verification to reduce timing differences.
- Legacy plaintext passwords are upgraded to a hash on successful login.
- Login never sends an OTP. `email_verified` is not checked.
- Login stores `session['auth_version']`; `login_required` compares it with `users.auth_version` and clears stale sessions after a password reset or a manual version bump.

### Account settings (removed)

- The `/account` page and route were removed along with the email-change form, the Account Settings navigation link, `templates/account.html`, and their tests.
- Users can no longer change their email in-app; the email captured at signup is the address used by Forgot Password.
- The `User` model and its fields (`username`, `password`, `email`, `email_verified`, `auth_version`) are unchanged, and no migration was needed.

### CSRF and security

- All forms include a hidden `csrf_token`; the global `CSRFProtect` enforces it.
- `forgot_password`, `reset_password`, and `reset_resend` are in `AUTH_ENDPOINTS`, so those pages are `noindex, nofollow` and send `Referrer-Policy: same-origin`.
- Existing authentication, password hashing, session lifetime, and memory behavior are unchanged.

### Migration

- Revision: `7c1a9e4b2f60` (`password reset and auth version`), down revision `fc35b4ffa9c0` (additive; history preserved).
- Adds `users.auth_version` (`INTEGER NOT NULL DEFAULT 1`) and the `password_resets` table: `id`, nullable indexed `user_id` FK to `users.uid`, indexed `email`, unique `token_hash`, `otp_hash`, `attempts`, `used`, `expires_at`, `last_sent_at`, `created_at`.
- Validated on a disposable SQLite database: `flask db upgrade` applies the full chain to `7c1a9e4b2f60`, `flask db check` reports no drift, and `downgrade` to `fc35b4ffa9c0` then `upgrade` again succeeds cleanly.
- **Not applied to Neon.** The reported production head remains `fc35b4ffa9c0`.
- Prior revision `fc35b4ffa9c0` added the `email_verifications` table, `users.email_verified` (`NOT NULL DEFAULT false`), and `NOT NULL` on `users.email`; it is reported applied to Neon on 2026-11-16 and was not independently verified in this session.

## 6. Current Deployment Status

### Vercel

- The project is deployed/reported as deployed on Vercel.
- The current HEAD is `d9ec607` (`master` is ahead of `origin/master` at `112a1b2`). The signup simplification and Forgot Password flow are uncommitted and not deployed.
- Vercel deployment of the signup simplification and Forgot Password flow is **not verified from this session**.
- The user reports that the Neon production migration completed with Alembic head `fc35b4ffa9c0`; the new `7c1a9e4b2f60` migration has **not** been applied.

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
69 passed
```

Test coverage includes:

- Resend email service: no-op when disabled or under test; sends the expected payload when enabled; returns `False` and does not log the OTP on provider failure.

- Signup creates the account immediately and redirects to login without sending email.
- Signup does not authenticate the new account.
- Signup stores `email_verified=False` and a normalized email.
- Signup hashes passwords; the internal username is `user:<normalized_email>`, with a numeric suffix on collision.
- Unverified accounts can log in by email.
- Signup requires a valid email and rejects invalid formats and duplicate emails.
- The signup page does not ask for a username.
- Forgot Password renders and is linked from the login page.
- A reset request for an existing email sends a 6-digit OTP and creates a session-bound challenge.
- A reset request for an unknown email creates a challenge but sends nothing and returns the same message.
- Only HMAC-SHA256 digests of the token and OTP are stored.
- Reset success hashes the new password, marks the challenge used, and redirects to login.
- Wrong, expired, reused, unknown-session, unknown-token, unknown-email, and changed-email cases are rejected.
- Attempt limits invalidate the challenge; resend enforces the cooldown, resets attempts, and invalidates the previous OTP.
- Password length and confirmation are validated without consuming attempts.
- Email-send failure consumes the challenge; the OTP is never logged.
- Password reset increments `auth_version` and invalidates existing sessions; `login_required` rejects a stale version.
- Forgot/reset/resend require CSRF.
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

> Update 2026-11-16: the user reports that the production Neon migration completed and the current Alembic head is `fc35b4ffa9c0`. The new `7c1a9e4b2f60` migration (auth version + password resets) is implemented and validated locally but has **not** been applied to Neon. The 2026-11-14 inspection below is retained as historical context; it was not rechecked in this session.

Last verified: 2026-11-14 during read-only backup/inspection. This was not rechecked during the current review.

- Database: Neon `neondb`
- Tables: `users`, `memories`
- Users: 7 rows
- Memories: 6 rows
- `users` columns: `uid`, `username`, `password`
- At that inspection there was no `email` column in production, which was why production signup/login returned HTTP 500 before the migration. The code defines `email` (NOT NULL) via migrations `6694a1a15bcb` and `fc35b4ffa9c0`; the user reports these are now applied.
- All 7 passwords were plaintext at inspection time
- No `alembic_version` table
- No password-reset-token table at inspection. The code now defines `password_resets` via migration `7c1a9e4b2f60`; it is not yet applied to Neon.
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
- Future migrations must be tested on a disposable database and applied to Neon only after a verified backup and explicit approval.
- The pre-migration reset plan in section 12 is retained as historical context. Do not delete production data or run migrations against Neon without explicit approval.
- Production database status: reported migrated to `fc35b4ffa9c0` on 2026-11-16; not independently verified in this session. Migration `7c1a9e4b2f60` must be applied before the new reset flow works in production. The historical details above describe the pre-migration state.

## 9. Features Still to Implement

### Email

- Implemented: required email column, login by email, signup with email/password only plus a generated internal username, and the Forgot Password flow (migrations `6694a1a15bcb`, `fc35b4ffa9c0`, and `7c1a9e4b2f60`).
- Account Settings (`/account`, email change) was implemented in Stage 3 and has since been removed; users cannot change their email in-app.
- The production migration is reported complete through `fc35b4ffa9c0`; `7c1a9e4b2f60` is local-only and has not been applied to Neon (see section 8).

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

### Forgot/reset password using Resend (implemented)

- Resend configuration and dependency were already present and are reused unchanged.
- Implemented single-use, expiring, HMAC-hashed reset challenges in `password_resets`.
- Implemented `users.auth_version` session invalidation.
- Implemented forgot-password, reset-password, and resend routes, templates, and rate limits.
- Responses do not reveal whether an email is registered.
- Tests cover expiry, reuse prevention, attempt limits, resend cooldown, and session invalidation.

### Frontend redesign with GSAP

- Redesign the current minimal templates.
- Add a same-origin CSS/JS asset structure.
- Add GSAP only after the backend flows are stable.
- Review CSP if any third-party scripts or styles are introduced.

### Database and migration work

- Flask-Migrate is now wired and `migrations/` is scaffolded with baseline revision `897fe5622bb6`.
- Email migration `6694a1a15bcb` (adds `users.email` + unique index `ix_users_email`), email-verification migration `fc35b4ffa9c0` (adds `email_verifications`, `users.email_verified`, and `NOT NULL` on `users.email`), and password-reset migration `7c1a9e4b2f60` (adds `users.auth_version` and `password_resets`) are implemented and validated locally. The user reports the first two applied to production (`fc35b4ffa9c0`); this was not independently verified in this session. `7c1a9e4b2f60` is **not applied**.
- `db.create_all()` at import was removed; schema is owned by migrations. Local setup now requires `flask --app app db upgrade`.
- The production reset plan in section 12 is retained as historical context. The signup simplification needs no schema change; the Forgot Password flow requires `7c1a9e4b2f60`.
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
- Use Cloudinary for photos/audio storage and Resend for password-reset email.
- Signup creates accounts immediately with email + password and sends no email; accounts are created with `email_verified=False`, and `email_verified` does not gate login.
- Invalidate sessions after a password reset by comparing `session['auth_version']` with `users.auth_version`.
- Keep the `EmailVerification` model/table as legacy data; do not drop it in this change.
- Use Upstash Redis with a `rediss://` TLS URL for shared rate limiting on Vercel.
- Never commit `.env`, credentials, database files, or backups.
- Back up Neon before database changes.
- Never execute migrations or password conversion against Neon without explicit approval.
- Implement features incrementally and run the full test suite after each change.

## 11. Exact Next Steps

1. Review and commit the uncommitted signup simplification and Forgot Password flow (`app.py`, `routes.py`, `services/otp.py`, templates, migration `7c1a9e4b2f60`, the affected tests, and this document), then push.
2. Vercel environment variables are configured: `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `RESEND_ENABLED=true`, and `OTP_SECRET` (see section 12). Confirm `RESEND_ENABLED` is exactly `true`/`1`/`yes`.
3. Verify a Resend sending domain for production; `onboarding@resend.dev` is testing-only (see section 12).
4. A Neon backup exists at `C:\Users\hp\Desktop\memoryvault_backup.dump`; verify it by restoring into a separate disposable PostgreSQL database, not just `pg_restore --list` (see section 12).
5. Back up Neon again, then apply migration `7c1a9e4b2f60` with explicit approval. The reported production head is `fc35b4ffa9c0`.
6. Verify production signup (immediate account creation, no email), login, and the Forgot Password flow over HTTPS.
7. Verify the 6-digit reset code email arrives from the verified sender domain.
8. Confirm auth responses send `Referrer-Policy: same-origin` and that session cookies are present.
9. Confirm Vercel has `RATELIMIT_STORAGE_URI` set to the Upstash Redis TLS URL, then redeploy if it changed.
10. Confirm `SECRET_KEY` and `OTP_SECRET` are stable across Vercel deployments and instances.

## 12. Production Reset and Deployment Plan (historical; reported completed 2026-11-16)

> This runbook is retained as historical context. The user reports that the production Neon migration completed with Alembic head `fc35b4ffa9c0`; it was not independently verified in this session. The migration chain now continues to `7c1a9e4b2f60` (auth version + password resets), which only needs an incremental `flask db upgrade` after a fresh backup — no reset is required for it.

The existing Neon data is disposable (approved). The plan is to verify the existing backup by restoring it into a separate disposable PostgreSQL database, then drop ONLY the four application objects and rebuild the schema from scratch with the full migration chain. The Stage 3 FIX code is already pushed (`3f719d7`).

> Prerequisite: `psql`, `pg_dump`, `pg_restore`, and `createdb` must be installed and on `PATH`. They are not present on the current Windows machine, so run these steps from an environment that has the PostgreSQL client tools.

> DESTRUCTIVE: Step 3 permanently deletes all `users`, `memories`, `email_verifications`, and migration history. It must run ONLY after Step 2 has produced a backup that has been successfully restored and verified. Do NOT run any step against Neon without explicit approval.

### Step 1 - Back up Neon (read-only)

```powershell
pg_dump "$env:PRODUCTION_DATABASE_URL" --format=custom --file "$env:USERPROFILE\Desktop\memoryvault_backup.dump"
```

The current backup lives at `C:\Users\hp\Desktop\memoryvault_backup.dump` (a valid `PGDMP` custom archive). Keep the filename used here consistent with the restore step below.

### Step 2 - Verify the backup by restoring it into a SEPARATE disposable PostgreSQL

`pg_restore --list` only lists the archive contents; it does NOT prove the dump restores. Always restore into a throwaway PostgreSQL database (never Neon) and compare counts.

```powershell
# Point these at a disposable local/scratch Postgres, NEVER Neon.
# Use an argument ARRAY: PowerShell would pass a single quoted "-h ... -U ..."
# string as one token, which breaks createdb/pg_restore/psql.
$localArgs = @("-h", "127.0.0.1", "-p", "5432", "-U", "postgres")
createdb @localArgs dmv_restore_check
pg_restore @localArgs --no-owner --dbname=dmv_restore_check "$env:USERPROFILE\Desktop\memoryvault_backup.dump"

# Compare against the pre-reset production inspection.
psql @localArgs -d dmv_restore_check -c "select (select count(*) from users) as users, (select count(*) from memories) as memories;"
psql @localArgs -d dmv_restore_check -c "select username, email from users order by uid;"
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

Expected chain: `897fe5622bb6` (initial) -> `6694a1a15bcb` (add users email) -> `fc35b4ffa9c0` (email verification) -> `7c1a9e4b2f60` (password reset and auth version, head).

### Step 5 - Deploy the application code (already done)

The Stage 3 FIX code was committed and pushed as `3f719d7 Implement email OTP signup verification`. Later changes (immediate signup and the Forgot Password flow) are currently uncommitted, so they must be committed and deployed before Step 6's new-flow checks apply; the `fc35b4ffa9c0` portions of this historical runbook were already deployed.

Vercel has no build hook for migrations, so `flask db upgrade` (step 4) must run as a manual release step. If only the incremental `7c1a9e4b2f60` revision is being applied, run the same command against Neon after a fresh backup (no reset needed).

### Step 6 - Verify

- `POST /signup` creates an unverified `User` immediately, sends no email, and redirects to `/login`.
- `POST /login` succeeds with email + password and no OTP, even when `email_verified` is false.
- `POST /forgot_password` sends a reset code only when the account exists and returns the same message either way.
- `POST /reset_password` with the correct code updates the password, invalidates existing sessions, and redirects to `/login`.
- Neon shows tables `users`, `memories`, `email_verifications`, `password_resets`, and `alembic_version` at `7c1a9e4b2f60`.

### Migration chain validated on fresh PostgreSQL (not only SQLite)

On 2026-11-15 the full chain was run against a fresh, disposable PostgreSQL 16.4 database:

- `flask db upgrade` -> `fc35b4ffa9c0` (head); `flask db check` -> no new operations.
- `flask db downgrade base` then `flask db upgrade` again -> head, cleanly.
- Tables: `alembic_version`, `email_verifications`, `memories`, `users`.
- `users`: `email varchar NOT NULL`, `email_verified boolean NOT NULL DEFAULT false`, unique `ix_users_email`, unique `users_username_key`.
- `email_verifications`: 11 `NOT NULL` columns; unique `email_verifications_token_key`; `ix_email_verifications_email`.
- A `pg_dump` -> `pg_restore` into a separate disposable database restored all rows and the revision `fc35b4ffa9c0`.

Revision `7c1a9e4b2f60` was validated on a disposable SQLite database:
`flask db upgrade` applied the full chain to head, `flask db check` reported no
drift, and `downgrade fc35b4ffa9c0` followed by `upgrade` succeeded. It has not
yet been run against PostgreSQL or Neon.

### Required production environment variables (Vercel)

- `RESEND_API_KEY` - Resend API key.
- `RESEND_FROM_EMAIL` - sender address on a verified domain (see below).
- `RESEND_ENABLED=true` - must be exactly `true` (or `1`/`yes`) for delivery; otherwise the app silently skips sending and password-reset codes are not delivered.
- `OTP_SECRET` - a dedicated random secret (for example `python -c "import secrets; print(secrets.token_urlsafe(48))"`). Falls back to `SECRET_KEY` when unset, but a dedicated value is required for production.
- Existing: `SECRET_KEY`, `DATABASE_URL`, `RATELIMIT_STORAGE_URI`; `SESSION_COOKIE_SECURE` is automatic on Vercel.

### Resend sender domain requirements (production)

- `onboarding@resend.dev` is a shared testing sender that Resend only delivers to the account owner's own email address. It cannot send to arbitrary users.
- Production requires a domain verified in Resend: add the domain, publish the required DNS records (SPF/DKIM, and DMARC as recommended), wait for verification, then set `RESEND_FROM_EMAIL` to an address on that verified domain (for example `no-reply@yourdomain.com`).
- Until the domain is verified, `POST /forgot_password` will not deliver reset codes to real users.

## 13. Photo Attachments Feature and Cloudinary Setup

### Architecture Overview

The Photo Attachments feature allows users to attach multiple photos to any memory, designating one photo as the primary cover photo.

Key architectural decisions:
1. **Direct Browser-to-Cloudinary Uploads**:
   - The Flask server NEVER receives, buffers, or stores raw image binaries.
   - When a user selects photos on the creation form, the client requests a short-lived signed upload payload from `POST /photos/signature`.
   - The server validates authentication (`@login_required`), enforces rate limits (120/hr), and signs valid Cloudinary upload parameters (`folder`, `timestamp`, `allowed_formats`) using `CLOUDINARY_API_SECRET` via SHA-1 HMAC. File size limits (`MAX_PHOTO_BYTES`) are enforced client-side in JavaScript before upload and strictly verified server-side in `normalize_photos`.
   - The browser uploads directly to Cloudinary's REST endpoint (`https://api.cloudinary.com/v1_1/<cloud_name>/image/upload`) using XMLHttpRequest, tracking individual file upload percentages with a native `<progress>` bar and reporting genuine Cloudinary API errors if encountered.
   - `CLOUDINARY_API_SECRET` is never sent to or visible in client-side code.
2. **Database Representation (`MemoryPhoto`)**:
   - Stores only `public_id`, `secure_url`, `is_cover`, `position`, `width`, `height`, `image_format`, and `bytes`.
   - Linked to `memories.mid` via foreign key with `ondelete='CASCADE'`.
   - `Memory.photos` uses `cascade='all, delete-orphan'` and is ordered by `position`.
   - Unique constraint on `public_id` prevents reusing the same asset across multiple memories or submissions.
3. **Cover Photo vs. Additional Photos**:
   - Each memory with photos has exactly one cover photo (`is_cover=True`).
   - If the user doesn't pick one explicitly, the first uploaded photo is automatically designated as cover.
   - **Cover Photo Visibility**: Visible on memory cards in `my_memories.html` and on `memory_detail.html` even when the memory is still locked.
   - **Additional Photos Privacy**: Strictly locked. On `memory_detail/<mid>`, if the memory is locked (`memory.open_date > today`), the backend queries ONLY the cover photo and sets `photos = []`. No additional photo URLs, IDs, or metadata are passed to Jinja or sent over the wire. Once unlocked, all additional photos render in an attractive responsive gallery with full-resolution links.
4. **Security & Ownership Validation**:
   - Uploads are scoped strictly to `memoryvault/users/<user_id>/...`.
   - Backend validation in `services/photos.py` (`normalize_photos`) ensures submitted `public_id`s begin with the authenticated user's exact folder prefix, prevents directory traversal, checks URL domain (`res.cloudinary.com`) and path, validates formats (`jpg`, `jpeg`, `png`, `webp`, `gif`), and enforces size and count limits.
   - Users cannot attach, view, or delete photos belonging to another user.
   - CSP headers permit `https://res.cloudinary.com` in `img-src` / `media-src` and `https://api.cloudinary.com` in `connect-src`.
5. **Asset Cleanup & Deletion**:
   - Deleting a memory via `POST /memory_detail/<mid>/delete` deletes the memory record and automatically triggers Cloudinary's Destroy API (`services/photos.py:destroy_photos`) to clean up all associated assets.
   - If memory creation fails during validation or database commit, an automatic cleanup routine (`_cleanup_uploads`) destroys any freshly uploaded assets in that user's folder that are not already bound to a database record, preventing orphaned Cloudinary assets.
6. **Graceful Degradation**:
   - If Cloudinary credentials are not configured, the create memory page notifies the user with a friendly notice, and memory creation works normally without photo attachments. The signature endpoint returns HTTP 503.

### Cloudinary Configuration & Environment Variables

Add the following to `.env` locally or in Vercel environment variables:

```bash
# Cloudinary Credentials (from Cloudinary Dashboard -> API Keys)
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret

# Optional Configuration (defaults applied if omitted)
CLOUDINARY_UPLOAD_FOLDER=memoryvault
MAX_PHOTOS_PER_MEMORY=10
MAX_PHOTO_BYTES=10485760
```

### Cloudinary Setup Instructions

1. Create a free account at [Cloudinary](https://cloudinary.com/).
2. Navigate to the **Dashboard** / **Settings -> Access Keys**.
3. Copy **Cloud Name**, **API Key**, and **API Secret**.
4. In your local `.env`, set:
   ```env
   CLOUDINARY_CLOUD_NAME=your_cloud_name
   CLOUDINARY_API_KEY=your_api_key
   CLOUDINARY_API_SECRET=your_api_secret
   ```
5. Ensure your Cloudinary security settings allow signed uploads to the specified upload folder (signed uploads are enabled by default on all standard Cloudinary accounts).

### Migration Details

- Revision ID: `a3f9c1d7e2b4`
- Revises: `7c1a9e4b2f60`
- File: `migrations/versions/a3f9c1d7e2b4_memory_photos.py`
- Creates table `memory_photos` with foreign key cascade to `memories.mid`, unique constraint on `public_id`, index on `memory_id`, and batch-alter table support for SQLite compatibility.
- Full migration chain:
  `897fe5622bb6` -> `6694a1a15bcb` -> `fc35b4ffa9c0` -> `7c1a9e4b2f60` -> `a3f9c1d7e2b4` (head)
- Fully validated locally with SQLite: `upgrade()`, `check()` (clean schema with zero drift), `downgrade(revision='7c1a9e4b2f60')`, and re-`upgrade()` all passed.
- **NEVER applied to Neon** in this session per instructions. When deploying to production after backing up Neon:
  ```powershell
  $env:DATABASE_URL = $env:PRODUCTION_DATABASE_URL
  $env:SECRET_KEY = $env:PRODUCTION_SECRET_KEY
  flask --app app db upgrade
  ```

### Automated Testing

- Test suite: `tests/test_photos.py` (22 photo-specific tests, 81 tests total across the project).
- Cloudinary interactions (`destroy_photo`) are mocked using pytest fixtures to guarantee offline and deterministic test execution.
- Tests cover:
  - Signature generation requires authentication and CSRF.
  - Signature returns HTTP 503 when Cloudinary credentials are missing.
  - Signature generation contains expected parameters and excludes `api_secret`.
  - Creating memory with photos and designated cover photo.
  - Fallback to first photo as cover when none selected.
  - Creating memory without photos still succeeds.
  - Enforcement of photo count limit (`MAX_PHOTOS_PER_MEMORY`).
  - Rejection of invalid file formats and oversized images.
  - Rejection of untrusted or spoofed Cloudinary URLs.
  - Rejection of photos belonging to another user's folder (`memoryvault/users/<other_user_id>`).
  - Rejection of duplicate photo payloads or photos already attached to an existing memory.
  - Rollback and cleanup of uploaded assets if database commit fails.
  - Locked memory detail strictly omits additional photos and hidden metadata from response.
  - Unlocked memory detail shows cover photo and responsive additional photo gallery.
  - Memory cards display cover photo and omit additional photo metadata.
  - Unauthorized users cannot view another user's memory or photos.
  - Deleting a memory cascades deletion to database photos and triggers Cloudinary asset destruction.
  - Unauthorized users cannot delete another user's memory.
  - Deletion requires valid CSRF token.

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
