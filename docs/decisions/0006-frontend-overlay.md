# ADR 0006: A checked source overlay for the DeerMate workspace

Date: 2026-10-26. Status: accepted. Requirements: FR-001/012/018, NFR-001/004/006.

The user requests a DeerMate frontend refactor using transitions-dev, transitions-polish and text-to-lottie. Keep the existing DeerFlow authentication, account preferences, conversation editor and background-task APIs. Introduce the secretary home as `/workspace`, with `/` redirecting there through the existing protected workspace layout. Do not maintain an unrelated second application or a deep upstream fork.

Version DeerMate-owned source in `frontend/overlay`, plus a small hash-checked patch manifest for upstream integration points. Apply it only to the disposable Git-archive build context, after validating every upstream file and anchor and rejecting symlinks/path escapes. Keep the upstream checkout, dependency lock and authentication behavior unchanged. Both local and ACK builds use the same Python helper. `build --frontend-only` shortens UI iteration without rebuilding the Gateway or mirroring helper images.

The first desk reads tasks from the latest 20 conversations, at most 20 records per conversation, and labels that bound. Partial/failed queries remain explicit; failed fetches never become successful zero counts. A configured MCP server does not prove an online device. Planned adapters remain visibly unavailable. The home prepares an account-scoped session draft using the existing composer store and opens the original editor; it does not submit model work, create a separate scheduler or put prompts in URLs. Task details show independently reported validation separately from an agent summary, with raw records available for inspection.

Use a small product-specific integration of the licensed transitions.dev tabs and motion scale, with reduced-motion/keyboard support. Author a transparent original Lottie scene, verify it in the official Skia Skottie player, and serve a pinned MIT lottie-web light player locally with a static SVG fallback. The skill collection and verification player are not redistributed. See [frontend provenance](../../frontend/NOTICE.md).

The local deployment now seeds extensions configuration into its owner-writable home volume: the upstream read API also needs a sibling lock file. Staging and credentials remain read-only to the Gateway; init reapplies the generated MCP seed on each `up`. Do not edit that managed file through the UI for persistent policy changes; edit the host-generated configuration instead. ACK already uses its writable managed home for this purpose.

This is a bounded first workbench view. Device liveness, full history pagination, cancel/resume/recovery controls, specialist routing and secretary-model acceptance require later work. Existing conversation controls remain reachable. See [M4.1](../specs/m4-workspace-refresh.md).
