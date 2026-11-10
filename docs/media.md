# README images and workspace tour

The README now shows **Workspace v2 running locally**, rather than the initial concept storyboard. All visible names, preferences, and followed topics belong to a dedicated demo account. No private account, model credential, fabricated assistant answer, or coding result appears in the recording.

## Current media

| Asset | Contents |
| --- | --- |
| [workspace.png](assets/readme/workspace.png) | Actual desktop assistant home, with the recent-items section collapsed using its normal control. |
| [memory-mobile.png](assets/readme/memory-mobile.png) | Actual memory page at a 390px viewport. |
| [workspace-tour.mp4](assets/readme/workspace-tour.mp4) | 22-second, silent H.264 walkthrough of the running interface. |
| [workspace-preview.gif](assets/readme/workspace-preview.gif) | Seven seconds from the same recording, optimized for GitHub's inline image preview. |

[Watch / download the MP4](https://github.com/mzydmer/deermate/blob/main/docs/assets/readme/workspace-tour.mp4). GitHub playback depends on the client; the README also provides a raw download link. The GIF is an excerpt, not a separate simulated animation.

## What happens in the video

1. Open the assistant home, with a real followed topic and three manually saved sample preferences.
2. Open **About you**, correct the answer preference, and wait for the actual save to complete through Go and DeerMem.
3. Return home and see the updated preference in the summary.
4. Create an empty **Temporary chat** and show its memory policy banner.

No chat model is called and no Native task runs. This clip demonstrates the interface and these storage operations; automatic extraction, tool selection, device connectivity, and Codex execution have [separate verification evidence](verification/README.md). The bottom caption is an editorial disclosure added by the capture script, not a product feature.

## Reproduce

Use a **fresh loopback-only test instance** with Workspace v2 images, an empty database, no configured models, and no enrolled devices. The ordinary [single-host bundle](single-host.md) can run with cached images; choose a separate project name and port, such as `deermate-readme` and `2046`. Keep its volumes separate from any personal installation. Initialize a synthetic administrator through the normal setup endpoint.

The capture script requires that administrator's private JSON file to contain `email`, `password`, `origin`, and `synthetic_owner: true`. The origin must match the loopback URL. Do not use production credentials or mark a personal account as synthetic.

```bash
python -m pip install -r requirements-media.txt
npm install --prefix .deermate/media-node playwright@1.62.1
.deermate/media-node/node_modules/.bin/playwright install chromium ffmpeg

DEERMATE_MEDIA_URL=http://localhost:2046 \
DEERMATE_MEDIA_ADMIN=/absolute/path/to/synthetic-admin.json \
DEERMATE_PLAYWRIGHT_MODULE="$PWD/.deermate/media-node/node_modules/playwright" \
node scripts/capture_readme.cjs

python scripts/render_readme.py
```

To use an installed Chrome, set `DEERMATE_BROWSER_EXECUTABLE` to its absolute executable path. The renderer uses system FFmpeg when available, then `imageio-ffmpeg`, or an explicit `--ffmpeg` path.

The capture tool creates a separate synthetic administrator, reconciles that account if interrupted, seeds real manual memories, and records actual browser actions. It blocks model submissions, rejects an instance with enrolled devices, and disables the demo account on exit. Temporary credentials and raw video remain under ignored `.deermate/readme-media/`; authentication cookies stay in memory. Stop the isolated test stack when finished; do not copy its database or credentials into the repository.

The renderer exports H.264/yuv420p with fast-start metadata and a smaller GIF excerpt. It decode-checks both, limits file sizes, and writes a [sanitized receipt](verification/readme-media-2026-11-10.json) with hashes. Review the desktop/mobile images and video frames before publishing. No runtime code is changed by these tools.

## Historical concept film

The October storyboard is retained for old links: [concept MP4](assets/deermate-concept.mp4), [GIF](assets/concept-preview.gif), [poster](assets/concept-poster.png), [hero](assets/hero.png), and [storyboard](assets/storyboard.png). Its labels, Python-first topology, planned integrations, and development stage describe that early proposal. They are **not the current architecture or capability statement**, and are no longer used in the README.

`scripts/render_concept.py` reproduces only that archived 24-second simulated film. It does not generate the current product tour or its screenshots.

## Provenance

The product interface, deer mark, capture tooling, and editorial captions are DeerMate assets. The current screenshots and video use the repository's design system. No third-party product logos, music, stock footage, private chats, or external account data are included. Fonts are resolved locally and are not redistributed. Original code and media are provided under the repository's MIT license.
