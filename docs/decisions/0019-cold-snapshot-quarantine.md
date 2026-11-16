# ADR 0019: Cold snapshots and quarantined restoration

- Status: accepted; implementation/acceptance tracked in Issue #4.
- Date: 2026-11-16.
- Requirements: NFR-005–007/010, FR-023/028/029/030–032.

## Context and decision

State spans Go/DeerFlow SQLite, checkpoints, DeerMem Markdown/FTS5, journals, model credentials and agent configuration. A single online database backup cannot establish one cross-file recovery point.

Use an explicit maintenance window: stop ingress and every application writer, reject another writer sharing the home, then archive the durable home and portable bundle configuration outside the source volume. Record immutable images, upstream, recovery time, unresolved operation identities and file hashes. Exclude only named rebuildable uv package caches; do not follow external links. Require acknowledgement for unresolved work and retain the original volume.

Freeze the input into a private temporary object; validate all content and tar metadata before creating a fresh target volume. Reuse that same object for configuration extraction and volume input. Recreate the canonical private topology using immutable images. Require the control image's `restore-quarantine-v1` capability. `DEERMATE_RESTORE_QUARANTINE=true` permits existing-owner authentication and reads, including read-only memory search, while blocking new work and mutations. All four Go background queues exit before polling; source synchronization is paused. Restored MCP profiles and telemetry are disabled, and application networking is isolated.

Reopening is an operator decision after checking original in-flight identities, source/device validity, secrets and forgetting since the snapshot. While dispatch stays frozen, the original authenticated/CSRF/versioned memory deletion and owner-scoped authorization revocation are allowed as narrow safety operations. Deletion synchronously applies only deterministic memory storage changes; no model or Native call is enabled, and all queues stay stopped. Unknown deletion reconciliation retains the same operation ID. External Worker/native state is not copied or restarted. Do not activate two controllers against the same devices or overwrite new work with old databases.

## Consequences

Cold backup entails downtime and independent storage. The archive contains private data and keys; checksum verification is neither encryption nor origin authentication. External TLS volumes, separately mounted credentials and device/native workspaces need their own inventory and recovery steps. Old snapshots may retain subsequently forgotten facts and need explicit retention/deletion policy.

This augments ADR 0008 without adding scheduled backups, cloud coupling or a new scheduler. API/memory/identity and dispatch evidence comes from `scripts/verify_single_host_restore.py`; a small local synthetic restoration is not a general RTO or disaster-recovery guarantee.
