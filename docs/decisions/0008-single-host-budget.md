# ADR 0008: An optional single-host budget deployment

- Date: 2026-10-26
- Status: Accepted as an optional deployment target. The owner separately approved cloud purchase and temporary SSH; bounded deployment acceptance completed 2026-10-27.

## Context

The owner rejected the initial ACK resource quote and requested the cheapest minimum configuration that can run the application. A personal trial does not require a managed Kubernetes control plane, cluster load balancer, NAT gateway or separate registry. Keep the ACK package for users who require it; do not silently submit a different cloud order.

## Decision

Generate a portable single-host Docker Compose bundle from the existing Go/Python/frontend/nginx images and the pinned upstream nginx configuration. Build on the existing build machine, transfer four prebuilt images, and use named volumes for SQLite/home and caches. Runtime ceilings total 1472 MiB and two CPUs. A 2 vCPU/2 GiB amd64 Linux server is a candidate, with actual host/model acceptance separate from constrained-container startup.

Keep Go login, management, CSRF and user scope. Bind only one loopback web port and begin with SSH forwarding. Generate fresh internal secrets, preserve an existing bundle, and do not copy native accounts, Worker credentials, model keys, databases or the local verification submit shim. The initial MCP/model configuration is empty; add only explicitly configured integrations later.

## Alternatives and consequences

Shrinking an ACK worker retains other cluster fixed costs. A 1 GiB host has not been validated; this profile budgets for a 2 GiB host instead. A single host avoids those components and is easier to move, but has no HA, managed backup or unattended failover. One-shot init runs as root only to set volume ownership; normal containers remain non-root and have no Docker socket. Docker/host administrators can read application state and secrets.

The bundle is a separate target, not a replacement for the native Mac verification profile. Cheap hosting does not remove model costs, renewal terms or the need for a reachable, verified home Worker. See [specification](../specs/single-host-minimal.md) and [operator guide](../single-host.md).

## Deployment follow-up · 2026-10-27

The selected SWAS host is running the four-service bundle. Initial HTTP/browser checks and a controlled full-host reboot passed; the OS reports 1613 MiB total memory. This does not change the single-host/no-HA decision or establish model/home Worker capacity. See the [target acceptance receipt](../verification/single-host-cloud-2026-10-27.json).
