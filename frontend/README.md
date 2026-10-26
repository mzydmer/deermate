# DeerMate workspace source

The product UI lives in `overlay/` and is applied to DeerFlow `a1b89d0` by [`frontend_overlay.py`](../scripts/frontend_overlay.py). `patches.json` verifies complete upstream file hashes before modifying integration points. Do not edit `.deermate/ack/deer-flow` or copy local credentials into the overlay. [ADR 0006](../docs/decisions/0006-frontend-overlay.md) explains the boundary; [NOTICE](NOTICE.md) records third-party provenance.

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
