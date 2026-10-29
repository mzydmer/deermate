# ADR 0012: One chat incarnation owns one coding session

Date: 2026-10-29. Status: accepted. Supersedes ADR 0011 only for chat-level
cardinality and selection among ambiguous histories; Worker child-task semantics
and independent per-round evidence remain unchanged.

The owner requires one conversation to stay associated with one Codex or Claude
session, and names derived from the first message with manual rename support.
Model instructions alone cannot enforce cardinality: an Agent can select the raw
submit tool again or issue concurrent tool calls.

Use the pinned runtime's **configured middleware** contract as the execution gate,
backed by an application-home SQLite admission journal. Do not use observation
plugin middleware, whose documented exception isolation can pass through to the
original tool. The configured guard never invokes the unguarded coding handler;
it uses the existing durable task service/ordinary driver with host identity. A
reservation precedes submission, deterministic tracking IDs reconcile duplicates,
and uncertain admissions remain blocked rather than being replayed. Include run
identity because some providers reuse tool-call IDs across runs.

Register coding connections explicitly. Freeze executor/server/project for each
user/thread/incarnation. Keep research tools and background-task controls. Native
session changes, a missing head or ambiguous legacy history require inspection;
they do not permit another root. Direct Worker/MCP administration remains a
trusted lower-level interface, outside this chat orchestration boundary. Claude's
discriminator is reserved for a compatible registered adapter; none is shipped.

Reuse the ordinary thread title and existing rename API/UI. Generate a short title
from the first human message in the runtime without a separate model call, and
preserve nonempty names on subsequent turns. Product names do not rename sessions
inside third-party clients. Go continues to own public authentication and APIs;
the policy gate, journal and view action are internal runtime integrations.

The policy journal must be backed up with the application home. Losing it does
not authorize new native work: adoption requires bounded complete, unambiguous
history. This conservative choice can require manual inspection after failures.
