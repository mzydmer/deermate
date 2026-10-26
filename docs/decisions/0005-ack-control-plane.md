# ADR 0005: Single-instance ACK control plane with the upstream Helm chart

Date: 2026-10-25. Status: accepted. Requirements: FR-012/FR-013, NFR-001/005/007.

The user requests Alibaba Cloud ACK deployment, superseding the initial recommendation to defer Kubernetes. Keep the home Worker loopback-only and use the existing enrolled SSH connector. The application processes still need to read task contents; deploying them in ACK does not add end-to-end secrecy from the application or model provider.

Reuse DeerFlow's exact previously verified commit, chart and Dockerfiles. Extend the backend image with the DeerMate wheel. A Python Helm 3 post-renderer adds the SSH Secret copy/mounts, managed MCP seed, retention annotations, private image pull references and admission checks. Keep upstream source/templates unchanged. Helm is deployment tooling; DeerMate-owned runtime and deployment code remain Python.

The initial profile has one Gateway and SQLite on a 20 GiB ACK block-storage PVC; Recreate prevents overlapping controller writers. Keep the embedded runtime/checkpoints persistent. Disable the sandbox provisioner and its RBAC, PostgreSQL, Redis, public ingress and service-account token automount. Use upstream authentication and localhost kubectl port-forward for first setup. This is a single-owner alpha profile, with downtime on upgrades, not an HA deployment.

Kubernetes projected Secrets use symlinks and group permissions, whereas the SSH client deliberately requires private ordinary credential files. A non-root init container copies only the expected files into a memory-backed emptyDir, directory 0700/files 0600. The Gateway mounts that copy read-only. Redeployment restarts it to refresh credentials; live Secret projection alone does not refresh copied files. Helm is the source of MCP configuration and reapplies its seed on every Pod start.

A standalone chart would duplicate the upstream application routing/authentication. NAS/RWX SQLite and multiple Gateway replicas would exceed the current evidence and storage contract. Public ingress, managed PostgreSQL and NAT enrollment can follow as independently specified changes.

Actual ACK provisioning, home account configuration, model availability and cloud-to-home reachability remain operator-specific acceptance steps. See [deployment spec](../specs/m2-ack-deployment.md).
