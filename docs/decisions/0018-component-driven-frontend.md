# ADR 0018: Component-driven frontend and semantic utilities

Date: 2026-11-12. Status: accepted for the isolated overhaul branch. NFR-008; issue #2.

YAML in design.md remains the sole visual source. Generate Tailwind v4 `@theme inline` mappings alongside CSS tokens and embedded recipes. DeerMate primitives wrap existing Radix/shadcn APIs, CVA defines variants, and tailwind-merge resolves caller composition. Do not replace upstream ui primitives or add npm dependencies. Features retain request/state logic and compose primitives/patterns; no native controls or visual utility combinations in features/routes.

Use canvas-soft for the workspace plane and canvas for cards, improving grouping without increasing shadows. Muted readable metadata changes to #666666 in light mode to meet the explicit caption contrast requirement; decorative mute is no longer used for required text. Document surfaces remain canvas. No global inversion.

Gate structure as well as values: controls/visual classes confined to primitives, one status mapping, dictionary copy, no resize or action underlines, bounded CSS beside components. Tests must cover DOM contracts and real layout, not only token strings. Existing motion provenance is retained and new feedback uses declared tokens with reduced-motion handling.

Consequences: more explicit component APIs and migration work; a token-only gate is insufficient. The development gallery is denied in normal production; synthetic fixture tests do not establish real provider compatibility. No merge or deployment is part of this decision.
