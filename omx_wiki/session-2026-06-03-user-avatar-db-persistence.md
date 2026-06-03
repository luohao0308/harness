# User Avatar DB Persistence

Category: `session-log`

Tags: `auth`, `user-profile`, `avatar`, `database`, `frontend`

## Summary

Login and registration remain database-backed: registration creates `users`, `organizations`, and `organization_members` rows, while login updates the user row's `last_login_at`. This slice adds avatar upload for real database users and stores the avatar bytes directly on the `users` table.

JWT access/refresh tokens remain client-held session credentials, not database session rows. Dev-token pseudo users still do not create or update user-profile rows.

## Delivered

- Added avatar storage columns on `users`: `avatar_mime_type`, `avatar_content`, `avatar_sha256`, and `avatar_updated_at`.
- Added Alembic migration `20260609_0036_add_user_avatar`.
- Added `POST /api/auth/me/avatar` to upload the current user's avatar.
- Kept avatar upload limited to JWT database-backed users; dev-token pseudo users, legacy dev user rows, and API key principals return 403 before any profile write.
- Accepted PNG, JPEG, WEBP, and GIF only, capped image content at 2 MiB, preflighted multipart bodies with a 2 MiB + 128 KiB request cap, and validated file magic bytes against the declared MIME type.
- Returned `avatar_data_url` from `/api/auth/me` and the upload endpoint so the Console can render the saved image after refresh.
- Parsed avatar multipart uploads through bounded `Request.stream()` handling instead of FastAPI `UploadFile`, avoiding pre-parsed oversized request bodies and avoiding a new `python-multipart` dependency.
- Added avatar upload UI under the top-right account menu for JWT sessions only.
- Added browser-side avatar preparation: image selections are resized to a 512px JPEG before upload when canvas support is available, with safe fallback to the original file if decoding or canvas output fails.
- Cleared the frontend file input after save and surfaced upload errors inside the account menu.
- Hardened frontend auth retry so JSON, multipart, team stream, wake stream, plan stream, and chat stream paths share refresh behavior.
- Fixed a multipart edge case where an explicit token equal to the stale stored JWT could be reused after refresh; retry now uses the refreshed stored JWT.

## Boundary

- Avatar image bytes are stored in the database, not on local disk or object storage.
- V1 does not add cropping, resizing, CDN delivery, public avatar URLs, or historical avatar versions.
- `/api/auth/me` returns the current user's avatar as a data URL; it does not expose arbitrary users' avatars.
- JWT tokens are not persisted as DB session rows. The durable login/register state is user/org/membership data plus user profile fields.
- Dev-token sessions are development-only and remain pseudo principals; they cannot upload avatars.
- API keys cannot update user avatars in V1; avatar update is a browser/JWT profile action.

## Verification

```text
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_auth_rbac_api_keys.py services/api-server/tests/test_auth_env_gate.py services/api-server/tests/test_first_admin_bootstrap.py -q -> 24 passed
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_auth_rbac_api_keys.py services/api-server/tests/test_auth_env_gate.py services/api-server/tests/test_first_admin_bootstrap.py -q -> 25 passed after 413 limit repair
services/api-server/.venv/bin/python -m ruff check services/api-server/app/api/auth.py services/api-server/app/api/schemas.py services/api-server/app/db/models.py services/api-server/tests/test_auth_rbac_api_keys.py services/api-server/alembic/versions/20260609_0036_add_user_avatar.py -> passed
services/api-server/.venv/bin/python -m ruff check services/api-server/app/api/auth.py services/api-server/tests/test_auth_rbac_api_keys.py -> passed after 413 limit repair
cd services/api-server && rm -f /tmp/harness-avatar.sqlite && DATABASE_URL=sqlite:////tmp/harness-avatar.sqlite .venv/bin/alembic upgrade head -> reached 20260609_0036
cd apps/agent-console && npm test -- api.test.ts ConsoleShell.render.test.tsx LoginPage.test.tsx RegisterPage.test.tsx routes.auth.test.tsx -> 25 passed
cd apps/agent-console && npm test -- avatarUpload.test.tsx ConsoleShell.render.test.tsx api.test.ts -> 19 passed after 413 limit repair
cd apps/agent-console && npm run lint -- --pretty false -> passed
cd apps/agent-console && npm run build -> passed
cd services/api-server && .venv/bin/alembic upgrade head -> local Postgres reached 20260609_0036
curl --noproxy '*' -sS http://127.0.0.1:8000/health -> {"status":"ok","service":"api-server"}
curl --noproxy '*' -sS -I http://127.0.0.1:5173/login -> HTTP 200
live API register/avatar upload smoke -> avatar_smoke=passed without printing JWTs
live API 600 KiB avatar upload smoke -> avatar_smoke_600k=passed without printing JWTs
independent reviewer -> PASS after JWT-only profile write and stream-parsed multipart limit fixes
```
