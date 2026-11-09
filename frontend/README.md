# DeerMate workspace source

All frontend work follows the repository [design.md](../design.md), including login, settings and the Go management page. Canonical tokens and component recipes live in the YAML frontmatter of `design.md`; CSS is generated into `overlay/src/styles/design-tokens.css`; run `python scripts/design_gate.py` and `python scripts/sync_design_tokens.py --check` at the repository root. Go embeds a generated copy of the same CSS. Update the guide and tokens together when changing the visual language.

The product UI lives in `overlay/` and is applied to DeerFlow `a1b89d0` by [`frontend_overlay.py`](../scripts/frontend_overlay.py). `patches.json` verifies complete upstream file hashes before modifying integration points. Do not edit `.deermate/ack/deer-flow` or copy local credentials into the overlay. [ADR 0006](../docs/decisions/0006-frontend-overlay.md) explains the boundary; [NOTICE](NOTICE.md) records third-party provenance.

The public `/docs` route contains the product guide, research-oriented technical design and changelog. Its only source is [`docs/product/`](../docs/product/guide/overview.md); regenerate the tracked frontend catalog with `python scripts/product_docs.py --write`, then verify `python scripts/product_docs.py --base <task-base>`. Read the mandatory [documentation policy](../docs/DOCUMENTATION_POLICY.md) on every change. Product docs are available from the login page, workspace header and sidebar without reading private runtime data.

For an initialized local Docker profile:

```bash
source .venv/bin/activate
python scripts/local_docker.py build --frontend-only
python scripts/local_docker.py up
```

Open [http://localhost:2026](http://localhost:2026). The root redirects to the authenticated workspace. Login uses the existing local owner account through Go; browser and SSR share the Go session. `/admin` provides user/role management. Chat-model configuration remains a separate step; preparing a draft does not invoke a model. The home reads tasks from the latest 20 conversations, at most 20 tasks each, and labels incomplete/error results.

UI acceptance is implemented in [`verify_frontend.cjs`](../scripts/verify_frontend.cjs). Run it in an isolated browser environment with Playwright 1.62.1 and environment variables `DEERMATE_URL` (local profile only), `DEERMATE_OWNER_FILE` (private generated owner file), `DEERMATE_PLAYWRIGHT_MODULE` (module path), and `DEERMATE_OUTPUT` (private screenshot/receipt directory). `DEERMATE_BROWSER_CONTAINER=1` permits Chromium's no-sandbox launch only inside the disposable container used for these checks. The script logs in, reads existing task evidence, tests draft handoff/filtering/themes/mobile/reduced motion, and injects isolated service failures. It does not submit model work or save cookies/passwords in its receipt. Raw screenshots can contain task content; only inspected bounded captures belong in docs.

## Motion authoring

`motion/generate.py` generates the original deer stroke greeting and one blink at `motion/public/projects/deermate/scene-1/lottie.json`. It is transparent, 128×128, 30 fps, 90 frames, one-shot. Regenerate with Python. The build copies it to `/deermate/secretary.json`; the product uses a static SVG when playback fails or reduced motion is enabled. The self-hosted player loads no external animation assets.

For authoring verification use the official `diffusionstudio/lottie` player at the revision in NOTICE. Copy the scene into its `public/projects/deermate/scene-1/`, install its dependencies, run its Vite dev server on loopback and use the printed port. Confirm the scene in `/__context`, then inspect `/deermate/scene-1?frame=0`, `?frame=45`, and `?frame=89` in that Skia player. Also verify the animation in the actual product renderer.

The sliding tab snippet preserves the skill's selectors, orchestration and reduced-motion guard. Product motion uses semantic timing: tabs 250ms; detail panel 400ms open / 350ms close; list stagger 40ms, capped at five offsets. The temporary loading spinner's continuous 1s linear cycle has no corresponding token usage and is intentionally separate. Do not import the entire transitions collection or remove accessibility guards.

## Retained acceptance

The [2026-10-26 receipt](../docs/verification/frontend-workspace-2026-10-26.json) binds source `fa452e3`, 16 real browser checks, inspected desktop/evidence/mobile/dark captures and official Skia pinned-frame/playback checks. The final local build recompiles current source with verified identical package/lock dependencies after registry stalls. [CI 40303558560](https://github.com/mzydmer/deermate/actions/runs/40303558560) separately completes the standard four-image build and all six jobs; its [probe receipt](../docs/verification/workspace-package-2026-10-26.json) is separate from interactive UI acceptance. Secretary-model and actual cloud acceptance remain deferred.

## Vercel-inspired baseline

The current visual direction is defined in [design.md](../design.md): neutral light/dark surfaces, sans-serif UI, meaningful status colors, 1px boundaries and readable control sizes. Login, workspace and Go management share tokens; upstream pages are migrated within the scope of future changes. This does not install or redistribute Vercel's internal UI library. The existing motion behavior remains; theme-only changes do not require reauthoring Lottie.


Personal-memory UI acceptance uses [`verify_memory_frontend.cjs`](../scripts/verify_memory_frontend.cjs) in a fresh local synthetic bundle. `DEERMATE_CAPTURE_FIXTURE=1` additionally checks an explicit chat request, its source link, source removal and cleanup; this mode requires an isolated offline model named `capture-fixture` and never belongs in a production configuration. The script checks that model before admitting one synthetic run. Existing instances, credentials and cloud models are not fixtures. The [capture receipt](../docs/verification/explicit-memory-capture-2026-11-02.json) separates Fake conversation admission from real-provider/native verification.


[`verify_memory_sdk.cjs`](../scripts/verify_memory_sdk.cjs) uses the same local fixture variables and an already initialized synthetic account with capture enabled. It types two messages into the actual chat composer, verifies the SDK streaming path, excludes the ordinary question and captures the second explicit request, then admits cleanup. It requires one offline `capture-fixture` model and records no message bodies or account secrets in its receipt. The two-turn check passed separately from the 14 management/source UI checks.


The [personal home](../docs/personal-home.md) keeps explicit attention topics beyond the recent-chat page and adds evidence-backed focus, opt-in goal suggestions and admitted actions. `verify_personal_home.cjs` uses the same synthetic fixture variables plus `DEERMATE_BROWSER_EXECUTABLE`; set `NODE_OPTIONS=--dns-result-order=ipv4first` when localhost resolves to IPv6 but the bundle publishes IPv4 only. It requires a separate loopback bundle with only `capture-fixture`, clicks real read-only follow-up/new-topic actions, and checks feedback, source loss, owner change, keyboard, mobile, dark and failed-refresh behavior. Each complete pass creates two offline Fake-model runs, zero real-provider/Native calls. Do not point it at a personal or production deployment.

## Continuous secretary entry

`continuous-secretary.tsx` connects the protected home to the persistent Router, work details, original-operation reconciliation, candidates and source/rule settings. It follows the existing neutral tokens, native controls and mobile single-column layout; no additional animation system is introduced. Server permissions/revisions determine execution buttons. Interactive secretary and manual work are available by default and inherit the conversation model. Background observation, automatic budgets and device grants remain separate; unconfigured devices are never shown as ready. Settings → Memory reuses the owner-scoped personal memory panel, including sources, correction and forgetting, without enabling capture. [Setup and current limits](../docs/continuous-secretary.md).

Follow-up drafts stay with their work. Continuing an existing native session requires an explicit next question. `continuous-intents.ts` retains the original request body and operation ID after an ambiguous response, including an execute-to-followup projection change. This in-memory protection ends when the component unmounts; after reload, inspect the authoritative original operation. Run its offline regression with Node 24+: `node scripts/verify_continuous_intents.mjs` from the repository root (also included in CI).

The [2026-11-04 UI receipt](../docs/verification/continuous-ui-2026-11-04.json) records actual Chrome 390/1280/1440px viewports, light/dark, keyboard and reduced-motion checks, work-specific drafts, ordinary-member isolation, and temporary nginx read faults followed by recovery. Eight state cards are presentation-only samples from [`continuous_fixture_ui.py`](../tests/continuous_fixture_ui.py), not execution/cancellation evidence. That script accepts an owner ID on stdin only inside a disposable single-user offline fixture, with no active Native task or usable grant. Do not run it in a personal deployment. The UI pass adds zero model runs or Native tasks. Real-source candidate acceptance and the remaining full CONT-16 matrix stay separate.

## Authenticated visual acceptance

The isolated fixture uses the production React bundle and real Go login/profile/authorization APIs, with synthetic loopback runtime data. It never loads a personal database or provider credentials and rejects run submissions. The browser scripts require its marker before login or mutations. This tests UI behavior; it does not prove real Gateway, provider or Native compatibility.

1. Build the current overlay with the pinned upstream integration patches and build Go control. The fixture uses `.deermate/design-system-20261105/frontend` and `.deermate/design-system-20261105/control`.
2. Run `python scripts/design_visual_fixture.py`. It refuses an existing `.deermate/design-auth-20261106` output directory and binds only loopback ports 3300–3303. Preserve or move earlier receipts before a fresh run.
3. Set `DEERMATE_PLAYWRIGHT_MODULE` and, where needed, `DEERMATE_BROWSER_EXECUTABLE`; run `node scripts/verify_authenticated_design.cjs` and `node scripts/verify_design_states.cjs`. Default URL is the fixture on port 3300.
4. Inspect synthetic screenshots and the JSON results, then stop the fixture. Credentials remain in its ignored private owner file; do not commit it.

The viewport/theme matrix covers login, workspace, task filters/evidence, all settings sections, draft-only chat, authenticated management and authorization pages. The state suite covers profile validation, memory create/search/correction/forget, loading/empty/failure and six task-detail states. Keyboard focus restoration waits for the actual close lifecycle rather than relying on a screenshot or a fixed delay.
