# DeerMate Go backend

Go owns the main HTTP entry, login/session management, users/roles, management APIs, workspace summary and management page. DeerFlow is the internal Python Agent runtime; Worker/MCP/SSH remain Python. React keeps its existing API shapes and calls Go for browser and SSR authentication. See [ADR 0007](../docs/decisions/0007-go-control-plane.md).

## Run

Use Go **1.27.3** for development:

```bash
cd backend
go test -race ./...
go vet ./...
go run ./cmd/deermate
```

The binary waits for runtime readiness before opening its pinned SQLite database. Configure variables through a private environment file or Secret:

| Variable | Purpose / default |
| --- | --- |
| `AUTH_JWT_SECRET` | Required, at least 32 characters; same signing secret as the internal runtime |
| `DEERMATE_RUNTIME_URL` | Fixed internal origin, default `http://127.0.0.1:8001` |
| `DEERMATE_DATABASE_PATH` | Runtime's local `deerflow.db`, default `./data/deerflow.db` |
| `DEERMATE_ORIGIN` | Browser origin, default `http://localhost:2026`; HTTPS enables Secure cookies |
| `DEERMATE_ALLOWED_HOSTS` | Explicit comma-separated host:port allowlist, including internal SSR and health hosts |
| `DEERMATE_LISTEN` | Default `:8080`; use a private network/loopback behind nginx |

The localhost origin is the reviewed Compose/ACK port-forward profile. Custom hostname/TLS deployment must update origin and host allowlists deliberately; arbitrary forwarded identity headers are not trusted.

For an existing local Docker profile, run at the repository root in its Python virtual environment:

```bash
python scripts/local_docker.py build --control-only
python scripts/local_docker.py up
python scripts/verify_go_control.py --restart
```

`up` takes an online SQLite backup at `data/backups/before-go-control.db` inside the existing home volume before first cutover. It preserves user IDs, password hashes, task ownership and preferences. Sign in again once: legacy browser JWTs are replaced with revocable opaque sessions. Keep the backup private. Rollback requires stopping the profile, backing up current state, then restoring deliberately; `down` does not restore or delete data.

## API modules

| Module | Routes |
| --- | --- |
| Auth | `/api/v1/auth`: `GET /setup-status`, `POST /initialize`, `POST /login/local` (form username/password/remember_me), `GET /me`, `POST /logout`, `POST /change-password` |
| Account | `GET/PATCH /api/v1/auth/preferences`, `GET /api/v1/auth/sessions`, `DELETE /api/v1/auth/sessions/{id}` |
| Management | `GET/POST /api/v1/admin/users`, `PATCH /api/v1/admin/users/{id}`, `POST /api/v1/admin/users/{id}/password`, `GET /api/v1/admin/audit` |
| Frontend | `GET /api/deermate/v1/info`, `GET /api/deermate/v1/workspace` (bounded summary of 20 threads) |
| Admin UI | `GET /admin`, administrator session required |
| Runtime adapter | Existing `/api/*` contracts, after authentication and role policy; auth/admin prefixes never fall through |
| Health | `GET /health/live`, `GET /health/ready`; `/deermate healthcheck` is the container probe |

Create user JSON: `{"email":"member@example.com","password":"a-private-12-plus-character-password","system_role":"user"}`. Patch accepts `system_role` and/or `disabled`; password reset accepts `password`. Creation currently accepts ASCII email addresses on ordinary DNS domains, matching the runtime's reserved-domain restrictions. No DNS lookup or email is sent.

Authenticated mutations need the session's `csrf_token` cookie value in `X-CSRF-Token`; preferences additionally require `X-Expected-User-Id`. Browser credentials are HttpOnly/SameSite cookies. Only digests of random session/CSRF tokens are stored. Password hashes are compatible with DeerFlow dfv2 and bounded legacy bcrypt. Login failures are throttled persistently. Password, role and suspension changes revoke sessions. The last active administrator is protected inside a serialized database transaction. Existing streams close within five seconds after revocation; admitted native work is not automatically stopped.

## Boundaries

This single-instance alpha has one Go service and one pinned runtime sharing local-disk SQLite. It is not an HA or arbitrary DeerFlow-version migration. Runtime requests receive short-lived real-user/version JWTs; browser-supplied internal identities and upstream auth cookies are stripped. Execution is admin-only until project-scoped grants exist; ordinary users can inspect their own threads/tasks and manage cosmetic preferences.

Public registration, OAuth providers, PAT/API-key login, email changes, MFA, recovery email and project-scoped execution grants are not implemented. Disabled legacy auth routes fail explicitly. Account/audit/session queries are bounded; enterprise audit retention/pagination is separate work. Mutations are not automatically retried. Closing a stream does not cancel the underlying task.
