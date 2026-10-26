# M4.1: DeerMate workspace and motion

Status: accepted; implementation in progress. Updated: 2026-10-26.
Requirements: FR-001/012/018, NFR-001/004/005/006.

The user requests installation of transitions-dev, transitions-polish and text-to-lottie, then a frontend refactor using them. Install the author's skills in the user's Codex skill directory; do not redistribute the skills as a library. Reuse the pinned DeerFlow frontend, authentication and task APIs through a versioned source overlay applied only to the generated build context. Keep the pinned checkout and lock unchanged.

Deliver a DeerMate login identity, a responsive secretary home, the existing conversation composer with account-scoped session draft handoff, a bounded view of real tasks from the latest 20 threads, status filters and task evidence details. Distinguish failed/partial fetches and unconfigured models from empty successful results. Keep new model execution behind the existing conversation submission. Configured MCP is not proof a Worker is online; planned adapters are clearly unavailable.

Use transitions-dev sliding tabs, transitions-polish semantic timing and asymmetric drawer timing, and a transparent original Lottie brand gesture. Preserve keyboard interaction, focus management, reduced motion, light/dark modes and static fallback. Verify the animation in the official Skia Skottie player at frame 0/midpoint/final, then in the actual application renderer. No cloud calls, model quota or new secret permissions are needed for frontend acceptance.

Acceptance: production frontend builds; real owner login works; authenticated API data is rendered; filters, detail panel, draft handoff and mobile navigation work; errors/unknowns remain explicit; no page errors, clipping or reduced-motion animation. Keep bounded screenshots/receipts and update STATUS. This is a first workbench view, not complete multi-agent routing, live device enrollment, recovery, mail or research automation.
