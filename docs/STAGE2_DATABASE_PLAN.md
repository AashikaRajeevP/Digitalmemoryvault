# Digital Memory Vault - Stage 2 Database Plan

Status: Draft / not yet applied to production.
Scope: Introduce controlled schema migrations (Flask-Migrate/Alembic) and plan the
incremental schema changes required by the Stage 2 features (email, password reset,
photo attachments, voice memories).

No production database (Neon) has been touched by this plan. Nothing in this
document may be applied to Neon without a verified backup and explicit approval.

## 1. Baseline already in the repository

The following has been implemented and validated locally against a disposable
SQLite database (not Neon):

- `Flask-Migrate` is wired in `app.py` via `migrate = Migrate(app, db)`.
- The import-time `db.create_all()` call was removed. Schema is now owned by
  migrations; the app no longer creates tables at import.
- `migrations/` was scaffolded with `flask db init` (standard Alembic layout).
- Baseline revision `897fe5622bb6` ("initial schema") reproduces the current
  production schema exactly:
  - `users(uid PK, username UNIQUE NOT NULL, password NOT NULL)`
  - `memories(mid PK, title NOT NULL, message NOT NULL, open_date NOT NULL,
    created_on NOT NULL, user_id FK -> users.uid NOT NULL)`
- Verified locally:
  - `flask db upgrade` creates `users`, `memories`, `alembic_version`.
  - `flask db downgrade base` removes them cleanly.
  - `flask db check` reports "No new upgrade operations detected" (models match
    the baseline migration).
  - `python -m pytest -q` -> 19 passed.

The baseline migration must be stamped (not re-run) against Neon, because the
tables already exist there. See section 6.

## 2. Goals and constraints

- Keep Flask, Jinja, SQLAlchemy, and the existing module-level `app` architecture.
- One small, reversible migration per feature; never a single "big bang" migration.
- Every migration must have a working `downgrade()`.
- Backfill columns as nullable first, backfill data, then tighten constraints in a
  later migration if needed.
- Never delete users or existing memories.
- Preserve date-locking behavior and ownership checks.
- Back up Neon and verify the backup before any production migration.
- Test every migration on a disposable database and show the SQL before applying
  to Neon. Wait for explicit approval.

## 3. Migration workflow (local and disposable DB)

Local setup (replaces the old implicit `create_all`):

```powershell
flask --app app db upgrade
```

If a local SQLite database already has `users`/`memories` but no `alembic_version`
table (created by the old `create_all`), stamp it as the baseline before upgrading
so Alembic does not try to recreate existing tables:

```powershell
flask --app app db stamp 897fe5622bb6
```

Create a new migration after editing models:

```powershell
flask --app app db migrate -m "short description"
flask --app app db upgrade
flask --app app db check
python -m pytest -q
```

Always review the generated script before committing. Autogenerate does not detect
every change (data migrations, some constraint/type changes), so treat output as a
draft and edit it.

Disposable-DB validation (never point at Neon):

```powershell
$env:DATABASE_URL="sqlite:///C:/Users/hp/AppData/Local/Temp/opencode/dmv-migrate/<name>.db"
flask --app app db upgrade
flask --app app db downgrade base
```

For PostgreSQL-specific behavior (indexes, types), also validate against a
throwaway local Postgres or a scratch Neon branch if available, since SQLite can
hide differences.

## 4. Planned migrations (ordered)

Each item below is one revision. Revision order may shift as features land.

### 4.1 Add index on `memories.user_id`

- Change: `op.create_index("ix_memories_user_id", "memories", ["user_id"])`.
- Rationale: every list/stats query filters by `user_id`; no index exists today.
- Downgrade: drop the index.
- Risk: low. Builds an index only; no data change.

### 4.2 Add `users.email` and email verification (IMPLEMENTED)

Status: implemented as `6694a1a15bcb` (add `users.email` + unique index
`ix_users_email`) and `fc35b4ffa9c0` (add `email_verifications`, add
`users.email_verified`, set `users.email` NOT NULL). The original plan to add a
nullable column and backfill was replaced by a full reset because production data is
disposable (approved). `email_verified_at` was not added; a boolean
`email_verified` plus the `email_verifications` challenge table is used instead.

- Change: `users.email` (NOT NULL, unique index), `users.email_verified`
  (NOT NULL DEFAULT false), and table `email_verifications` (token UNIQUE,
  username, email indexed, password_hash, otp_hash, attempts, used, expires_at,
  last_sent_at, created_at).
- Downgrade: drop the table, drop `email_verified`, and make `email` nullable.
- Risk: medium. Requires a clean reset (approved) because `email` is NOT NULL.
- Config/UI: signup OTP verification, login by email, account settings page.

### 4.3 Add `users.auth_version` (session invalidation)

- Change: add `auth_version` INTEGER NOT NULL with `server_default="1"`.
- Rationale: password reset and "log out everywhere" invalidate existing sessions
  by comparing the session's stored version against the row.
- App change: store `auth_version` in the session at login; `login_required`
  compares and clears the session on mismatch.
- Downgrade: drop the column.
- Risk: low. Defaulted column, no manual backfill needed.

### 4.4 Add `password_reset_tokens`

- Columns: `id` PK, `user_id` FK -> users.uid, `token_hash` (store a hash, never
  the raw token), `created_at`, `expires_at`, `used_at` (nullable).
- Index on `token_hash` (unique) and `user_id`.
- Single-use: set `used_at` on consumption; reject expired/used tokens.
- Rate limit forgot-password and reset-password routes; avoid account enumeration.
- Downgrade: drop the table.
- Risk: low. New table; no effect on existing rows.

### 4.5 Add `photos` (Cloudinary metadata)

- Columns: `id` PK, `memory_id` FK -> memories.mid, `user_id` FK -> users.uid,
  `public_id` (Cloudinary id), `secure_url`, `width`, `height`, `bytes`,
  `format`, `is_cover` (boolean default false), `created_at`.
- Indexes: `memory_id`, `user_id`.
- Enforce at the app layer: 10 MB per photo, 10 photos per memory, one cover.
- Ownership: every read/write filters by the owning user; non-owners never get
  URLs for locked memories.
- Downgrade: drop the table.
- Risk: medium. Requires Cloudinary config and a CSP review (already permits
  `res.cloudinary.com` and `api.cloudinary.com`).
- Config: raise/route-scope `MAX_CONTENT_LENGTH` (currently 2 MB) before uploads.

### 4.6 Add `audio_memories` (voice recordings)

- Columns: `id` PK, `memory_id` FK, `user_id` FK, `public_id`, `secure_url`,
  `duration_seconds`, `bytes`, `created_at`.
- Indexes: `memory_id`, `user_id`.
- Enforce at the app layer: 25 MB and 10 minutes per audio memory.
- Keep audio inaccessible until the memory unlocks; owner preview rules to be
  decided alongside photo preview rules.
- Downgrade: drop the table.
- Risk: medium. Storage/streaming and `Permissions-Policy` (microphone already
  allowed for self).

## 5. Config and dependency changes (outside the schema)

- `MAX_CONTENT_LENGTH`: raise or make route-specific before photo/audio uploads.
- Cloudinary: add dependency and environment configuration; keep secrets out of git.
- Resend: add dependency and environment configuration for reset emails.
- Update `requirements.txt` for each new dependency and pin versions.
- Review CSP if a third-party Cloudinary upload widget is introduced.

## 6. Production (Neon) procedure - requires approval

Do not perform any of these steps without a verified backup and explicit approval.
The authoritative, step-by-step runbook is `PROJECT_STATUS.md` section 12. Summary:

1. Take a fresh Neon backup with `pg_dump --format=custom`.
2. Verify the backup by restoring it into a SEPARATE disposable PostgreSQL database
   and comparing row counts. `pg_restore --list` is not sufficient verification.
3. Because the existing production data is disposable (approved), reset ONLY the
   application objects instead of stamping the legacy schema:
   `DROP TABLE IF EXISTS email_verifications, memories, users, alembic_version CASCADE;`
   (drop `memories` before `users`; do not use `DROP SCHEMA public CASCADE`).
4. Apply the full chain from base: `flask --app app db upgrade` -> head
   `fc35b4ffa9c0`.
5. Verify the live schema and smoke-test signup/login/memory flows.
6. Keep the pre-reset backup until the change is confirmed healthy.

The full chain `897fe5622bb6 -> 6694a1a15bcb -> fc35b4ffa9c0` has been validated
against a fresh, disposable PostgreSQL 16.4 database (not only SQLite), including
`flask db check`, `downgrade base`, re-`upgrade`, and a `pg_dump`/`pg_restore`
round-trip. See `PROJECT_STATUS.md` section 12.

Deployment gap to resolve before the first production migration: the repository has
no `vercel.json` and no build step that runs `flask db upgrade`. Migrations must run
as a manual release step before the new code is served. Until then, run
`flask --app app db upgrade` manually against Neon as an approved, backed-up
operation.

## 7. Test strategy

- Keep the current `tests/conftest.py` approach (temporary SQLite, CSRF and rate
  limiting disabled for behavior tests) and continue using `db.create_all()` in the
  fixture so tests do not depend on migration state.
- Add focused tests per feature (email validation, reset token expiry/reuse,
  session invalidation via `auth_version`, photo ownership and limits, audio
  unlock gating).
- Add a migration smoke test that runs `upgrade` then `downgrade` on a disposable
  database for the new revisions.
- Never run tests against Neon.

## 8. Rollout order (recommended)

1. Reset Neon to base and apply the full chain (approval required) - see section 6
   and `PROJECT_STATUS.md` section 12. Superseded the original "baseline stamp"
   approach because production data is disposable.
2. `users.email` + `email_verifications` (signup OTP) + account settings UI -
   DONE (`6694a1a15bcb`, `fc35b4ffa9c0`).
3. `memories.user_id` index.
4. `users.auth_version` + session invalidation.
5. `password_reset_tokens` + Resend flows.
6. `photos` + Cloudinary uploads and CSP/config review.
7. `audio_memories` + browser recording/playback.
8. Frontend redesign with GSAP after backend flows are stable.

## 9. Open questions

- Email verification: resolved - required at signup via a 6-digit OTP (`fc35b4ffa9c0`).
- Cover-photo selection UX and locked-memory photo preview rules.
- Retention policy for reset tokens and expired/used rows.
- Whether to automate `flask db upgrade` in the Vercel release step.
