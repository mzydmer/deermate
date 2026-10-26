# ADR 0007: Go-owned main, management and frontend API backend

Date: 2026-10-26. Status: accepted; supersedes ADR 0001 for the control plane.

The owner changes the language requirement: main backend, management backend, account/login management and frontend-facing interfaces should use Go. Use a single Go binary with explicit auth/account/admin/workspace/runtime-adapter modules. Keep the React UI and delegate Agent capabilities to pinned DeerFlow and the existing Worker; this preserves the validated native lifecycle without porting a large external application.

Go owns login verification, revocable opaque browser sessions, user lifecycle, RBAC, CSRF, audit and the public API boundary. It uses the compatible shared SQLite users/preferences tables so original UUIDs and task ownership survive, adding namespaced session/audit/throttle tables. DeerFlow's public auth/admin routes are intercepted by Go. Its internal runtime receives only short-lived user-bound JWTs and still checks real user/version/ownership. Do not forward the runtime's broad internal identity or client-supplied identity headers.

Shared SQLite is intentionally a transitional same-node single-control-plane layout: one Go service and one runtime, WAL/busy timeout, one cloud-disk writer topology with Recreate. It does not claim HA or arbitrary cross-version database compatibility. Unknown users schemas fail closed. Future PostgreSQL and a dedicated identity-provider contract can remove this pinned table coupling.

New non-admin users can inspect their own data and edit cosmetic preferences; the shared single-owner Worker is not silently granted to them. Go restricts execution/configuration to administrators until project-scoped grants are designed. The runtime's own RBAC and ownership remain an additional boundary.

See [migration spec](../specs/go-control-plane.md). Python Worker/MCP/SSH and deployment tooling remain explicit integration components; broader Worker-language migration is a separate scope decision.
