# ADR 0010: Optional temporary outbound SSH home Worker link

Date: 2026-10-28. Status: proposed; prepared only, deployment authorization pending.

## Context

The real secretary model can dispatch through the local Docker MCP/SSH path, but the home Worker has no directly reachable cloud SSH endpoint. ADR 0004 remains the default direct transport. The current cloud admin grant explicitly disallows reverse forwarding and cannot be reused to silently add access.

## Proposed decision

For a separately approved 24-hour acceptance, use two dedicated OpenSSH accounts/keys. A Mac-initiated reverse connection binds only cloud `127.0.0.1:18778` to the Mac's existing loopback Worker. A cloud reader account permits only forwarding to that listener, so the existing enrolled AsyncSSH/MCP transport can be reused from Docker without a host-network container or public Worker port.

Disable shell/exec/subsystem, sudo, password, PTY, Agent/X11, socket and tunnel-device authority for both accounts. Pin the previously verified cloud host key and existing Worker instance/token; preserve Worker project admission and task lifecycles. Expiring authorized keys reject new logins; a persistent timer additionally removes these keys and terminates their account sessions at the deadline. The existing admin key is not extended.

## Alternatives and consequences

Direct home SSH needs reachable networking and a separately provisioned home OS account. A public Worker HTTP port adds unnecessary exposure. Docker host networking would change runtime isolation/listening. A new device-pairing/relay protocol is a larger design and authentication surface. This temporary option reuses deployed SSH and the existing HTTP contract while keeping those projects separate.

Both SSH legs terminate at the trusted cloud host; the cloud sees plaintext and holds single-owner Worker authority. A reverse key constrains the cloud listener, not the client's ultimate local destination; the home connector remains trusted. This is manually provisioned alpha acceptance, not automatic pairing, production tenancy or unattended permanent device management. It needs explicit owner approval of the added login/forwarding grants and actual restricted-account/network/expiry checks before claiming cloud-to-home operation.

See the [reviewable scope and acceptance plan](../specs/m2-home-reverse-link.md). Preparing private key/configuration files alone grants no access.
