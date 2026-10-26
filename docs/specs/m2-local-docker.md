# M2.5: Local Docker startup and real Worker acceptance

- Status: implemented and locally verified; see retained receipt and STATUS.
- Requirements: FR-004/006/009/012/013, NFR-001/004/005/007.
- Updated: 2026-10-26. User authorized installing Docker, starting the project locally and verifying actual execution; cloud credentials will follow separately. User selected page/login/real Codex acceptance, with secretary-model configuration deferred.

## Scope

Install the official Intel Mac Docker Desktop in the user Applications directory. Reuse the ACK Gateway/frontend/nginx images in a loopback-only Compose stack with persistent named volumes, normal setup/login and no Docker socket or host-directory mount. Stage an explicit allowlist of generated configuration and dedicated SSH credentials through the Docker API into a named volume. A separately running host Worker uses the existing local Codex login on one generated test project. A generated-key loopback SSH development server connects it to the container's enrolled MCP client.

No API key is inferred from a Codex/ChatGPT login. Without an independently supplied secretary model configuration, keep models empty and label chat-model selection/notification as untested. A local-only protected submit adapter may replace model selection for backend verification; it must require both the current authenticated owner and a separate local verification key, and must not be installed in the ACK image/default Gateway.

## Acceptance

1. Docker daemon, Compose and Buildx work locally; a real container runs.
2. The same pinned upstream/DeerMate images build locally. Only nginx publishes `127.0.0.1:2026`; all application runtime containers are non-root and have no Docker socket or unrestricted host mounts.
3. Setup/login, rejected anonymous access, frontend delivery, MCP discovery and SSH Worker identity are checked.
4. A real Codex repair passes independent configured validation and returns a patch through actual Gateway tracking → MCP → SSH → host Worker. Preserve bounded evidence; credentials and raw/private logs remain ignored.
5. Gateway restart preserves account, SQL task identity and result. Reusing an accepted idempotency key cannot start another native task.
6. Provide repeatable start/status/verify/stop commands. Stop only this profile's containers/native processes; retain state and other Docker resources.

Actual cloud/ACK, OS OpenSSH account policy, NAT, desktop automation and real secretary-model conversation remain separate claims. Record any installation/UI limitation accurately; a headless health check is not a browser login check.

## Observed acceptance

The 14-check Gateway/SSH receipt includes a real Codex repair, independent passing unittest, retained diff, same Worker handle/attempt on duplicate submission, and account/SQL result across Gateway restart. The upstream enforces one tracking owner per remote handle; the local shim returns a scoped HTTP 409 for duplicates rather than creating another row. The verifier reuses a saved submission key after uncertain interruption.

An isolated Linux Chromium browser rendered the actual login page, submitted the generated local owner credentials, reached `/workspace/chats/new`, and confirmed an authenticated session with no page errors. It used a fresh browser context in the private Compose network, without accessing the locked Mac desktop or user browser data. UI branding remains upstream DeerFlow. See [local guide](../local-docker.md) and [receipt](../verification/local-docker-2026-10-26.json).
