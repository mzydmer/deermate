# Concept film and original media

The README film is a **24-second motion storyboard**, not a recording of implemented software. All requests, tasks, device names, execution states, and outputs are simulated. A disclosure appears throughout the video and GIF. No actual account content or agent execution is shown.

## Assets

| File | Use |
| --- | --- |
| [hero.png](assets/hero.png) | README header artwork |
| [concept-preview.gif](assets/concept-preview.gif) | An animated README preview linking to the MP4 |
| [deermate-concept.mp4](assets/deermate-concept.mp4) | 1280 × 720, H.264, 12 fps, 24 seconds, silent |
| [concept-poster.png](assets/concept-poster.png) | Single simulated dashboard frame |
| [storyboard.png](assets/storyboard.png) | Contact sheet of all six scenes |

## Storyboard

1. **00–04s:** DeerMate positioning: one private assistant, your agents, your machines.
2. **04–08s:** A user describes the intended maintenance task.
3. **08–12s:** Specialist role routing: design, implementation, execution, and review.
4. **12–16s:** Proposed Python and SSH worker topology.
5. **16–20s:** A simulated task dashboard.
6. **20–24s:** Intended evidence: diff, tests, and sources; actual project stage disclosed.

## Regenerate

Use Python 3.11 or newer. The renderer supports Arial on macOS or DejaVu Sans on Linux. Font differences can change line breaks and pixels; inspect the output after regeneration.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-media.txt
python scripts/render_concept.py
```

To render PNG/GIF assets without FFmpeg:

```bash
python scripts/render_concept.py --skip-video
```

`imageio-ffmpeg` supplies the FFmpeg executable used to encode and decode-check the MP4. Generated assets are committed so the README does not depend on a build service. The GitHub README links to the MP4 file viewer with a download fallback; inline MP4 playback behavior depends on the GitHub client.

## Provenance

The layout, deer mark, storyboard, animation, and text were created for DeerMate with the included Python source. No third-party product logos, UI recordings, music, or stock assets are included. Fonts are resolved locally and are not redistributed. Code and generated original artwork are provided under the repository's MIT license.
