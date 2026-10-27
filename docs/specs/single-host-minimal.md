# Minimal single-host deployment

- Status: implemented; bounded local startup/API/restart checks passed. No server purchased or deployed.
- Requirements: FR-009, FR-012, NFR-001, NFR-005–NFR-007.
- User direction: lowest-cost configuration sufficient for a personal trial; the earlier ACK quote was rejected.

Prepare a portable four-service Docker Compose bundle from the same pinned, prebuilt Go/Gateway/frontend/nginx images. A 2 vCPU/2 GiB Linux host is a candidate, subject to actual startup and workload checks. Compile images on the existing build machine. Use its bundled system disk and network, without managed Kubernetes, NAT gateways, load balancers, a registry service, or a managed database. Keep the existing ACK package as an optional target.

Acceptance:

1. Runtime memory ceilings sum to 1472 MiB, leaving nominal space on a 2 GiB host for Docker/OS; Node has a bounded heap. This is a budget, not proof of real 2 GiB VM performance.
2. Keep Go authentication/management and shared SQLite identity. Publish only localhost on an explicit unprivileged port; initial access uses a matching SSH local forward. Python runtime, Go internal API and frontend have no host port.
3. No host Codex/Worker credentials, private messages, old runtime database or model keys enter the bundle. Fresh secrets are owner-only; no local submit shim, Docker socket, privileged mode or automatic native execution. Worker/MCP defaults empty.
4. Use fresh named volumes for validation; preserve the running local deployment and its data. Verify startup, owner setup/login, admin access, anonymous rejection and restart persistence under the configured limits.
5. Do not equate an idle-memory sample or constrained containers on an 8 GiB Docker VM with a real 2 GiB host, a model workload, a cloud deployment or a reachable home Worker. Record those separately.
6. Purchase/terms, SSH account setup and any public exposure are separate from local bundle preparation. Record the actual account checkout quote and any coupon/renewal exclusions before purchase.
