# ADR 0004: Enrolled SSH forwarding and instance-bound remote task handles

Date: 2026-10-25. Status: accepted; M2.2 implementation. Requirements: FR-013 and AC-M2-02.

## Context

The Worker already owns durable state, project admission, native execution and authenticated loopback HTTP. Remote access must preserve those boundaries and task identities while adding host authentication, encrypted transport and explicit revocation behavior. An authenticated connection can survive removal of its server authorized key, and a reused host/port can accidentally point at a new Worker database.

## Decision

- Use optional AsyncSSH local TCP forwarding from a controller loopback port to the configured remote `127.0.0.1:worker_port`. Reuse HTTPX and the existing API instead of inventing HTTP framing or another RPC protocol. The temporary local listener still requires the Worker bearer token.
- Keep one administrator-owned enrollment per worker: explicit host, port, user, known_hosts, dedicated client key, token reference, application instance identity and expiry. Disable ambient SSH config/agents, alternate authentication and agent forwarding.
- Add stable instance identity in SQLite metadata. It identifies a database/task namespace and is not an authentication secret. Pin SSH host keys separately.
- Bind remote MCP task handles as `instance_id:task_id`, accepted by the pinned DeerFlow driver. Local MCP IDs remain unchanged. Re-enrollment cannot reinterpret an old handle as another Worker's task.
- Recheck admission and credential/trust material for every HTTP operation. Recheck application identity before forwarding. Changed enrollment fields require a fresh controller/MCP process; changed file contents force SSH reauthentication.
- Close cached connections on a timer (default 60 seconds), grant expiry or rejected access. Connection expiry waits for the bounded in-flight HTTP operation to release its lock. Removing a server key alone cannot promise instant revocation of an authenticated channel; operators must terminate it for immediate revocation.
- Do not automatically retry HTTP mutations after any transport failure. A lost acknowledgement leaves an unknown outcome; an explicit retry must reuse its idempotency key. Native execution continues independently within the admitted Worker deadline after access revocation.

## Alternatives

| Alternative | Reason not chosen |
| --- | --- |
| Public HTTP/MCP listener with a new authentication stack | Widens network exposure before remote identity and deployment are proven |
| Execute remote shell commands or SFTP to read tokens | Grants more host authority than forwarding an existing API requires |
| New SSH stdio RPC framing | Duplicates the established API and recovery semantics |
| Bare task IDs across mutable worker bindings | Cannot detect accidental reassignment after controller restart |
| Unbounded authenticated SSH sessions | Server key removal would leave access available indefinitely |

## Consequences

Administrators must provision the remote service account, restricted SSH forwarding policy, verified host key and token through a trusted channel. Current code does not create accounts, edit sshd, configure routers or implement NAT/reverse tunnels. SSH endpoints can see plaintext, and the copied API token grants the single owner's Worker authority. Dedicated OS accounts/VMs remain deployment concerns.

Real temporary SSH protocol, HTTP and MCP tests use generated keys and an offline native fixture. They do not prove an operator's OpenSSH configuration, actual two-machine deployment, NAT, production isolation, hard-crash recovery, or model/UI behavior. See [spec](../specs/m2-ssh-worker.md) and [setup](../ssh-worker.md).
