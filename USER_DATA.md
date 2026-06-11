# Where User Data Lives in PlaceUp

This doc is the source of truth for "where is X stored, and who can modify it?".
Pair it with [`/privacy`](https://placeupcareer.com/privacy) — the privacy policy
is the public-facing version of the same info.

## Storage layout

All user-owned data lives in **Google Cloud Firestore** in the project
`placeup-firebase-641222668282`, database `(default)`. Aggregated job
postings (no PII) live in **Cloud SQL Postgres** instance `placeup-backend`
in `steel-shine-492401-u6`.

### Firestore collections

| Collection | What it holds | Key | When written | Cascade-deleted with account? |
|---|---|---|---|---|
| `users` | name, email, password_hash (bcrypt), plan, email_verified, profile fields | `user_id` (uuid) | signup, profile edit, password change | ✅ |
| `user_preferences` | target_roles, target_locations, notification toggles | `user_id` | first preferences fetch (auto-seeded), save in Settings | ✅ |
| `user_alert_settings` | per-channel notification on/off flags | `user_id` | toggles in Alerts page | ✅ |
| `user_alerts` | per-job notifications, read/unread state | random | when a new high-match job lands | ✅ |
| `user_resumes` | filename, score, parsed_text, active flag | random | resume upload / activate / delete | ✅ |
| `user_applications` | tracked applications (status, salary, notes) | random | when user clicks Apply on a job | ✅ |
| `auth_sessions` | refresh-token hash + revocation state | random | every signin, refresh, signout | ✅ (revoked + deleted) |
| `password_resets` | sha256(reset_token), expires_at | sha256 hex | forgot-password request | ✅ |
| `email_verifications` | sha256(verification_token), expires_at | sha256 hex | signup, resend-verification | ✅ |

We never store plaintext passwords or plaintext reset/verification tokens.
The tokens go on the wire only inside the email link; the server holds
SHA-256 hashes so a DB dump cannot be used to mint password resets.

### Cloud SQL tables (job data, no PII)

| Table | What it holds | PII? |
|---|---|---|
| `master_jobs` | deduped (title, company, location) job postings | ❌ |
| `jobs` | per-source raw scrapes before dedup | ❌ |
| `silver_posts` | Firestore→Postgres synced job postings | ❌ |
| `companies` | company name lookup | ❌ |
| `staging_records` | raw scraper payloads + validation status | ❌ |
| `ingest_runs` | scraper run metadata (counts, status) | ❌ |
| `contacts` | recruiter contact enrichment results | ❌ (uses public info) |

## User-facing controls

Everything below is available from `/dashboard/settings`:

| Action | UI | Backend route | Behaviour |
|---|---|---|---|
| Update profile | Settings → Profile Information | `PUT /api/user/profile` | Whitelist-filtered field update on `users` doc |
| Change password | Settings → Security | `PUT /api/user/password` | Verifies current password, hashes new, **revokes all other sessions** |
| Forgot password | Settings → Security → "Send reset link" OR `/forgot-password` page | `POST /api/auth/forgot-password` | Emails one-time link, 30-min expiry, hash-stored |
| Reset password | `/reset-password?token=…` (link from email) | `POST /api/auth/reset-password` | Consumes token (one-time), revokes all refresh tokens |
| Resend verification | Settings → Email & Account | `POST /api/auth/resend-verification` | 48-hour expiry, hash-stored |
| Verify email | `/verify-email?token=…` (link from email) | `POST /api/auth/verify-email` | Sets `users[uid].email_verified = true` |
| Delete account | Settings → Danger Zone | `DELETE /api/user/account` | Requires password confirmation. Cascades through every collection above. Returns per-collection delete counts. |
| Upload / delete resume | Resumes page | `POST/DELETE /api/user/resumes/...` | Direct on `user_resumes` |
| Track application | Job detail → Apply modal | `POST /api/user/applications` | Direct on `user_applications` |

## Programmatic deletion contract

`user_store.delete_user(user_id: str) -> dict[str, int]` is the single
function that removes everything for a user. It returns a per-collection
count of deleted docs so the API logs (and the user-visible response)
have an audit trail. Implementation: `backend/app/db/firestore_user_store.py`.

Order of operations inside `delete_user`:
1. Revoke active `auth_sessions` first (so any in-flight access tokens
   stop being able to refresh).
2. Wipe each user-owned collection (`user_preferences`, `user_alert_settings`,
   `user_alerts`, `user_resumes`, `user_applications`, `auth_sessions`,
   `password_resets`, `email_verifications`).
3. Delete the `users` doc itself.

The function is **hard-delete** by design — the privacy policy promises
immediate removal, so there is no soft-delete flag.

## What's NOT in the database

- **Plaintext passwords** — bcrypt-hashed only.
- **Plaintext reset / verification tokens** — sha256-hashed.
- **Resume PDFs / DOCX binaries** — only the parsed text. Original files are
  never persisted (Cloud Run containers are ephemeral; uploads are parsed
  in-memory then discarded).
- **Payment card numbers** — Stripe handles this. We only see Stripe's
  customer_id + subscription_id.
- **Third-party OAuth refresh tokens** — Google/LinkedIn OAuth is not
  currently enabled in the UI.

## How to access your own data

Email `privacy@placeupcareer.com` for a data-subject access request. We will
return a JSON export of every Firestore document we hold for your user_id
within 30 days, in line with GDPR Article 15 / CCPA §1798.110.

## How to verify the cascade locally

```bash
# Dry run — count what WOULD be deleted, no writes.
python -c "
from app.db import user_store
user = user_store.get_user_by_email('test@example.com')
if user:
    counts = user_store.delete_user(user['id'])
    print(counts)
"
```
