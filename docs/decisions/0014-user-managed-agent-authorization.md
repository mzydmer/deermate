# ADR 0014 User managed Agent authorization and outbound HTTPS transport

Date: 2026-11-03. Status: Accepted. Implementation and deployment evidence remain separate in STATUS.

## Context

The approved temporary SSH link expired and cloud credential cleanup obscured its user-facing cause. The owner requested user-selected expiry, visible connection details, implementation and deployment. Extending the historical 24-hour lease would not deliver those controls.

## Decision

Go owns user authorization, versions, pending changes, revocation and history. A device uses an outgoing authenticated HTTPS poll to the existing trusted control plane, avoiding a new public Worker listener, new cloud SSH credentials, or changes to Mac sshd. Reuse the existing Worker task lifecycle and MCP ordinary driver with instance-bound handles. Pairing is short-lived and single-use; the device owner explicitly confirms the exact policy before it becomes active.

Enforce scope in Go and in the loopback Worker. Local full-authority Worker credentials stay on the device. The connector only forwards a fixed allowlist of Worker operations; the cloud registry accepts project IDs from the device's registered catalog. Local permission observations expire within 90 seconds and use both local clocks plus observed server time. Delivered mutations are never automatically requeued. Request loss remains an uncertain outcome, reconciled with the existing native task/key.

The installation has one device owner. Reserve that identity on pairing/import, reject another administrator's platform execution/configuration, and check it in the session middleware before coding admission. This does not implement multi-user device sharing.

The management page is a Go-embedded `/admin/agents` page using the canonical design tokens, alongside the existing Go `/admin` page. This preserves existing frontend images while making the feature discoverable from account management. Broader React settings integration remains a presentation follow-up.

## Alternatives and consequences

Direct SSH remains available under ADR 0004. ADR 0010 remains the historical manual acceptance topology and is not silently renewed. Generating new SSH account policies and cleanup timers for every UI change would require another privileged provisioning service; the outbound transport keeps runtime grants independent of deployment administrator access.

Both HTTPS endpoints and the trusted cloud application see task plaintext. Device identity credentials persist until replaced; MCP credentials change per grant version, and current authorization is checked for every operation. Automatic periodic identity rotation, background reminders, OS startup supervision, shared project grants and production tenant isolation are separate work, not assumed features. Expiry/revocation does not mean a native process has stopped until its task evidence confirms that fact.
