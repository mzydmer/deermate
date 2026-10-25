# Security model proposal

Status: Worker, MCP and enrolled direct SSH transport alpha. Bearer authentication, local Host/Origin checks, project admission, native sandbox policies and single-owner state remain in force. Broader deployment requirements below are not all implemented or independently audited. Updated: 2026-10-25. See [local limits](local-worker.md) and [SSH scope](ssh-worker.md).

The M2.1 stdio MCP bridge uses that same single owner's local bearer authority. It forwards to a fixed loopback endpoint with proxy discovery and redirects disabled, and does not add a network listener, new grants, or direct database access. Run it only in a trusted local DeerFlow process with deliberate access to the Worker token; its three tools can act on that owner's registered projects/tasks. Bounded summaries may still contain project content; no universal redaction is claimed. See [the setup and deployment limits](deerflow.md).

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

The direct transport uses AsyncSSH, explicit known_hosts/client keys and an enrolled instance ID; it does not introduce cryptography. It disables ambient identities and non-key authentication, rechecks grants and credentials per operation, and bounds cached connection lifetime. Instance IDs prevent namespace drift, not host impersonation; host-key validation provides host authentication. SSH endpoints see plaintext. Relay deployment, automatic key enrollment, penetration testing and audit completion are not claimed.

Revocation rejects new remote operations and closes the controller tunnel; already admitted Worker tasks continue under existing limits. Removing a server authorized key alone does not disconnect authenticated sessions. The default 60-second connection lifetime bounds reauthentication, subject to bounded in-flight HTTP cleanup; immediate server-side revocation requires terminating active sessions. Dedicated restricted accounts and trusted provisioning remain operator responsibilities. Tests use generated keys and a temporary protocol server, not the operator's sshd.

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
