# Go control plane migration

Status: implemented; local integration verified, final regression/delivery in progress. Updated: 2026-10-26.
Requirements: FR-001/003/009/012/018, NFR-001/005/006/007.

The owner now requests Go for the main backend, management backend, user/login management and frontend-facing interfaces. This explicitly supersedes the Python-owned control-plane constraint. Keep the existing React frontend, DeerFlow as an internal Python Agent runtime, and the verified Python Worker/MCP/SSH adapter as the explicit internal execution integration boundary.

Deliver one Go modular control-plane binary: authentication/session, account/admin, workspace API and a guarded runtime adapter. Main and admin are distinct route modules and permissions, not separately duplicated user stores. The browser and frontend SSR call Go. Agent conversation/planning/execution remains delegated to the internal runtime through per-user credentials; this is not a claim that DeerFlow itself has been ported to Go.

## Data and authorization

- Reuse the pinned users table and original UUIDs, password hashes, roles and preferences so task ownership/history survives. Go owns account writes, opaque browser sessions, login throttling and audit records; the runtime reads compatible identities from the same local SQLite database. Retain one Go instance and the existing single-runtime, local-disk/Recreate deployment boundary.
- Go browser sessions are revocable random tokens stored as digests, with HttpOnly/SameSite cookies, request-origin checks and session-bound CSRF. Preserve password compatibility with DeerFlow dfv2 and bounded legacy bcrypt. Password changes, suspension and role changes revoke sessions. Protect the last active administrator atomically.
- Proxy requests use a short-lived user/version-bound runtime JWT. Strip client-supplied identity/internal/bearer headers, never use the runtime's omnipotent internal principal for browser requests, never expose the bridge credential in cookies/responses, and retain runtime owner filtering. New users have read-only runtime access until project-scoped execution grants exist; execution and configuration stay admin-only in this single-owner Worker alpha.
- Disable uncontrolled public registration. First-admin creation is atomic; admin create/list/update/reset, own password/session management and bounded audit queries are implemented in Go. Preserve existing frontend endpoint/response shapes where used. Unsupported OAuth/PAT paths fail explicitly instead of reaching legacy auth.
- Keep existing data and take a SQLite backup before local cutover. Existing legacy browser JWTs require one new login. Do not reset the owner password, rewrite task IDs, replay work or consume model quota to prove a UI/API migration.

## Acceptance

1. Go tests cover initial-owner races, hash compatibility, CSRF/origin, session restart/logout/revocation, account roles/disable/reset and last-admin invariants.
2. The reverse proxy preserves streaming and original owner identity; forged headers and route escapes cannot reach an admin/internal identity. A regular user cannot execute work or read another user's records.
3. Existing owner logs in through Go, reads the original real task/evidence, changes preferences, and uses Go admin APIs/UI; suspension and logout take immediate effect.
4. Local Docker uses Go as the only public API/auth entry while runtime/Worker stay private; original frontend login/workspace checks pass. ACK rendering/build configuration includes the same control plane; actual cloud deployment remains pending credentials.
5. Update architecture, ADRs, README, agent guidance and retained verification with actual scope and results. Do not label the remaining Python runtime/Worker as Go implementations.
