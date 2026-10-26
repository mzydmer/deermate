# M2.4: ACK control-plane deployment package

- Status: implemented; local Chart/policy checks and Linux image CI passed. Actual ACK installation pending operator environment.
- Requirements: FR-009, FR-012, FR-013; NFR-001, NFR-002, NFR-005–NFR-007.
- Updated: 2026-10-25. User explicitly requested Alibaba Cloud ACK deployment scripts.

## Scope

Package the pinned DeerFlow application for a single-owner ACK managed cluster with ordinary Linux ECS nodes. Run its Gateway/embedded runtime, frontend and reverse proxy; keep native Codex execution on the separately enrolled Worker. Reuse the pinned official Helm chart and Dockerfiles. DeerMate adds its Python SSH/MCP package to the backend image and applies a small Python Helm post-renderer instead of forking upstream templates.

The quick profile is one Gateway, SQLite/checkpoints on one 20 GiB RWO cloud disk, Recreate updates, authenticated upstream setup/login, ClusterIP and localhost port-forward. Provisioner, cluster-wide execution RBAC, PostgreSQL, Redis and public ingress are disabled. Only the configured MCP execution path is exposed to the secretary; no local bash/file toolset is configured. A model-compatible endpoint must be supplied by the operator. Worker enrollment is optional during initial UI installation, then enabled explicitly with trusted host identity and credentials.

User instruction supersedes the earlier architecture's recommendation to defer Kubernetes. This changes deployment scope, not permission to connect to an unspecified cluster or modify home machines.

## Acceptance

1. A Python CLI initializes ignored configuration, prepares the exact upstream commit, builds/pushes images, renders review manifests, installs/upgrades, shows status and opens a localhost port-forward. Target context is explicit; prepare/build/render do not query or mutate a cluster.
2. Public example configuration contains no secrets. Model key and optional SSH key passphrase come from private files; credentials enter Kubernetes Secrets without command-line literals or printed manifests. SSH Secret data is copied to owner-only ordinary files in an in-memory volume by a non-root init container.
3. One Gateway, Recreate, block storage and persistent checkpoints are enforced. The renderer rejects namespace drift, unexpected application RBAC/public services and widened local tool configuration. Pod service-account token mounting is disabled; default ingress is disabled.
4. Upgrades reapply Helm-managed MCP config and restart the Gateway so enrollment/Secret changes become effective. SQLite home and app-key Secret carry retention annotations. No automatic retry of native task mutations is added.
5. Tests render the actual pinned chart and check effective Kubernetes resources, app config and credential copy behavior; CI builds the extended backend and upstream frontend and probes the backend without real credentials or model calls.
6. Publish ACK/ACR prerequisites, exact commands, troubleshooting, removal/backup boundaries and SSH/NAT limitations. Record separately: local render/tests, Linux image checks, and actual ACK installation (only when performed).

This package does not create/bill a cluster, claim actual ACK installation, configure NAT/reverse tunnels, deploy a desktop Worker in Kubernetes, or establish a real-model/chat/SSH acceptance result merely by starting the UI.

## Recorded evidence

Local: 14 deployment tests including both actual pinned Chart modes; ordinary suite 86 passed/6 skipped; generated configuration accepted by the pinned upstream AppConfig; Helm 3.19.0 real post-renderer output checked. Linux CI [40266316155](https://github.com/mzydmer/deermate/actions/runs/40266316155), commit `ca23f2c`, built all four amd64 images and passed non-root Gateway readiness/authentication/MCP/SSH/credential-copy probes. All six CI jobs passed. See [retained artifact-derived evidence](../verification/ack-package-2026-10-25.json) and [STATUS](../STATUS.md). ARM image builds, ACR push, actual Kubernetes installation, frontend login, real model and home SSH remain unverified.
