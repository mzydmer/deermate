# Security model proposal

Status: local worker alpha with bearer authentication, local Host/Origin checks, configured project admission, native Codex sandbox policies, and single-owner state. Remote transport and the broader requirements below remain unimplemented; nothing has been independently audited. Updated: 2026-10-25. See [local limits](local-worker.md).

## What must be protected

Personal messages and source code, external-service credentials, host access, project integrity, task results, and the user's authority to decide who can act. Task metadata can itself reveal sensitive information even if the task payload is encrypted.

## Trust boundaries

| Boundary | Proposed property | Important limit |
| --- | --- | --- |
| User to DeerFlow/control service | Authenticated access with explicit grants | The service processing a task can read it |
| Control service to worker | SSH encryption and pinned host keys | Both SSH endpoints can read task content |
| Optional forwarding relay | Forward encrypted SSH traffic without termination | Can observe traffic timing and disrupt availability |
| Worker to external agent | Limited account, project roots, runtime restrictions | An agent can exercise all permissions of its process |
| Agent to model provider | Provider's supported encrypted transport | The provider receives prompts and relevant context |
| Optional Hermesh MCP gateway | Self-hosted gateway with scoped grants | The gateway holds keys and can read/act within those grants |

The proposed direct SSH path is not a new cryptographic protocol. No encrypted-relay, key-management, penetration-test, or audit completion is claimed. A TLS-terminating proxy is a plaintext endpoint; calling it self-hosted does not make it blind to content.

## Admission and execution requirements

- Deny unknown workers and host-key mismatches; never use an accept-all known-hosts callback.
- Enroll keys through a trusted channel; define rotation, expiry, revocation, and device-loss recovery before remote release.
- Resolve project IDs to administrator-configured roots. Task text cannot supply arbitrary host paths or command templates.
- Use structured subprocess arguments, not shell interpolation of model text.
- Keep controller and worker service accounts separate from the user's everyday account.
- Enforce limits on runtime, concurrent jobs, input size, event size, attachment size, and artifact access.
- Worktrees prevent edit collisions, not credential access. Use a container, VM, or OS sandbox where isolation is required.
- Never treat a message from a worker or model as permission to widen access.
- An expired or revoked grant must reject new operations. Existing work needs an explicit policy for stop versus allowed completion.

## Untrusted input

Issues, PRs, repository files, dependencies, email, websites, images, and agent output may contain prompt injection. Research tools receive the smallest practical authority. Tool admission, credentials, and writable paths must be controlled outside the language-model prompt. External content cannot create new grants or authorize publishing.

An independent reviewer checks the patch and acceptance evidence; it is not assumed immune to prompt injection. Automatically approving another model's request is not a replacement for a worker permission boundary.

## Recovery, side effects, and cancellation

Persist a task/session mapping before launching. Reconcile after a timeout or reconnect rather than replaying blindly. Deduplicate event deliveries and write operations. Record uncertain outcomes explicitly. A cancellation request remains pending until the worker reports interruption; a disconnected machine may continue working and must not be falsely displayed as stopped.

## Logging and secrets

Keep secret values out of committed configuration, ordinary logs, and video fixtures. Do not copy entire local credential directories into workers. Use supported local sign-in flows or secret references. Redaction is best effort and does not justify recording secrets in the first place. Protect local databases and artifacts with OS permissions; disk encryption and backup encryption remain deployment concerns.

## Desktop execution

Screen recording, accessibility access, and app logins widen authority. Run desktop tasks in a dedicated user/VM session; lock a session to one task at a time. A screenshot can contain private information. Do not expose a desktop control service directly to the public internet.

## Optional Hermesh bridge

Hermesh is independently maintained. Its CLI connection is designed for encrypted endpoint-to-endpoint traffic through a relay; its remote MCP gateway holds a connection key and can decrypt sessions within its grant. Hermesh explicitly does not provide an execution sandbox. Verify the deployed upstream version and configuration rather than inheriting a marketing claim.

Source: [Hermesh README](https://github.com/hermeshai/hermesh#security) and [MCP gateway design](https://github.com/hermeshai/hermesh/blob/main/docs/mcp-gateway.md).

See [SECURITY.md](../SECURITY.md) for reporting guidance.
