# Frontend component overhaul

- Status: implemented and locally accepted; PR #10, no main merge or deployment.
- Requirement: NFR-008; all API, permission and recovery contracts retained.
- Tracking: https://github.com/mzydmer/deermate/issues/2
- Base: 66d3088; upstream a1b89d0432de4e45adc59f512cb25bb386ea1e51.
- Updated: 2026-11-12.

## Problem and outcome

Native controls and page-specific CSS bypass the existing design recipes. Build typed primitives and reusable shell/composer/inspector/feedback patterns; migrate features while preserving their data flow. Token compliance does not establish visual quality.

## Scope and contract

React overlay, login, documents, Go management/authorization and tooling UI. Wrap existing shadcn/Radix; no upstream primitive replacement, lockfile change or new npm dependencies. Features retain endpoint paths, request bodies, operation IDs, uncertainty journals, source/deletion barriers, temporary-topic policy and server permissions/revisions. No real-provider/Native invocation, personal data, main merge or deployment.

## Layers and acceptance

- [x] O-01: YAML-generated Tailwind semantics, typed primitives with DOM tests and development-only gallery.
- [x] O-02: reusable 240/64px/drawer shell, 64px header, compact rows, content-sized composer and Inspector.
- [x] O-03: feature/route native controls, dm-text-button and inline bilingual calls eliminated; dictionary and status map shared.
- [x] O-04: deermate.css deleted after migration; CSS budget and layer enforcement with negative cases.
- [x] O-05: Go/extension surfaces use generated recipes.
- [x] O-06: synthetic browser matrix at 390/768/1024/1280/1440 in both themes, long content, >=4.5 contrast, keyboard and reduced-motion. Retain before/after screenshots privately and inspect them.
- [x] O-07: portable prepare/install/build/dev/fixture command, semantic verifier selectors.

## Failure behavior and authority

Loading skeletons; empty reason; retained data and retry on partial failure. Execution ended, validation passed/failed, unknown, expired, cancelled and deployed remain distinct. Fixtures bind loopback and refuse existing/private data; no new capabilities or fake controls. Screenshot checks do not certify full accessibility or real runtime compatibility.

## Stages and validation

P0 inventory/spec/environment; P1 primitives/mapping/tests/gallery; P2 patterns/shell; P3 features/copy/verifiers; P4 embedded surfaces; P5 stricter gate/regression. Commit separately. Use DOM tests, existing behavioral verifiers, production build and design/document/Go/Python checks. O-01–O-07 are locally accepted; actual command results, screenshots and CI scope belong in STATUS/EVOLUTION.

## Inventory at base

| Overlay file | Lines | Native controls | dm references | Inline copy calls |
| --- | ---: | ---: | ---: | ---: |
| `src/app/docs/[...slug]/page.tsx` | 31 | 0 | 0 | 1 |
| `src/app/docs/layout.tsx` | 15 | 0 | 0 | 0 |
| `src/app/docs/page.tsx` | 5 | 0 | 0 | 0 |
| `src/app/page.tsx` | 5 | 0 | 0 | 1 |
| `src/app/workspace/chats/[thread_id]/page.tsx` | 5 | 0 | 0 | 0 |
| `src/app/workspace/memory/page.tsx` | 2 | 0 | 0 | 0 |
| `src/app/workspace/page.tsx` | 11 | 0 | 0 | 0 |
| `src/app/workspace/work/page.tsx` | 2 | 0 | 0 | 0 |
| `src/components/deermate/auth-frame.tsx` | 59 | 0 | 8 | 0 |
| `src/components/deermate/brand.tsx` | 103 | 0 | 3 | 0 |
| `src/components/deermate/continuous-intents.ts` | 48 | 0 | 0 | 0 |
| `src/components/deermate/continuous-secretary.tsx` | 847 | 23 | 53 | 104 |
| `src/components/deermate/desk.tsx` | 1 | 0 | 0 | 0 |
| `src/components/deermate/goal-suggestions.tsx` | 153 | 2 | 6 | 6 |
| `src/components/deermate/motion-tabs.tsx` | 79 | 1 | 2 | 0 |
| `src/components/deermate/personal-home.tsx` | 818 | 24 | 43 | 48 |
| `src/components/deermate/personal-memory.tsx` | 739 | 26 | 39 | 46 |
| `src/components/deermate/product-docs.tsx` | 322 | 4 | 29 | 0 |
| `src/components/deermate/secretary-conversation.tsx` | 262 | 5 | 18 | 12 |
| `src/components/deermate/task-detail.tsx` | 210 | 3 | 13 | 0 |
| `src/components/deermate/workspace-api.ts` | 18 | 0 | 0 | 0 |
| `src/components/deermate/workspace-assistant.tsx` | 465 | 5 | 41 | 26 |
| `src/components/deermate/workspace-memory.tsx` | 489 | 6 | 28 | 18 |
| `src/components/deermate/workspace-work.tsx` | 178 | 3 | 13 | 18 |
| `src/components/workspace/settings/memory-settings-page.tsx` | 23 | 0 | 2 | 0 |
| `src/components/workspace/welcome.tsx` | 36 | 0 | 2 | 1 |
| `src/components/workspace/workspace-header.tsx` | 57 | 0 | 2 | 0 |
| `src/components/workspace/workspace-nav-chat-list.tsx` | 104 | 0 | 0 | 0 |
| `src/components/workspace/workspace-sidebar.tsx` | 72 | 2 | 1 | 0 |
| `src/styles/deermate.css` | 1750 | 0 | 492 | 0 |
| `src/styles/design-components.css` | 67 | 0 | 0 | 0 |
| `src/styles/design-system.css` | 179 | 0 | 1 | 0 |
| `src/styles/design-tokens.css` | 279 | 0 | 52 | 0 |
| `src/styles/product-docs.css` | 574 | 0 | 179 | 0 |
