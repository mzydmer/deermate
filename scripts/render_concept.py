#!/usr/bin/env python3
"""Render original concept media. No live product or agent execution is shown."""

from __future__ import annotations

import argparse
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets"
W, H, FPS, SECONDS = 1280, 720, 12, 24
BG, PANEL, LINE = "#0c171b", "#14262b", "#294047"
WHITE, MUTED, GREEN, GOLD = "#edf6ee", "#a1b8b5", "#9bf2c1", "#efd699"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        if bold else
        ["/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    )
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise RuntimeError("Install Arial or DejaVu Sans to render this storyboard.")


FONTS = {(s, b): font(s, b) for s in [14, 16, 18, 20, 22, 24, 28, 30, 34, 40, 44, 56, 62, 74, 88] for b in [False, True]}


def text(d: ImageDraw.ImageDraw, xy, value, size=22, fill=WHITE, bold=False):
    d.text(xy, value, font=FONTS[size, bold], fill=fill)


def wrap(d, xy, value, width, size=22, fill=WHITE, bold=False, gap=9):
    words, line, y = value.split(), "", xy[1]
    for word in words:
        candidate = (line + " " + word).strip()
        if d.textlength(candidate, font=FONTS[size, bold]) > width and line:
            text(d, (xy[0], y), line, size, fill, bold)
            line, y = word, y + size + gap
        else:
            line = candidate
    if line:
        text(d, (xy[0], y), line, size, fill, bold)
    return y + size


def box(d, bounds, fill=PANEL, outline=LINE, radius=18):
    d.rounded_rectangle(bounds, radius=radius, fill=fill, outline=outline, width=1)


def pill(d, xy, value, color=GREEN, background="#203d33"):
    width = int(d.textlength(value, font=FONTS[16, True])) + 28
    box(d, (xy[0], xy[1], xy[0] + width, xy[1] + 31), background, background, 15)
    text(d, (xy[0] + 14, xy[1] + 6), value, 16, color, True)
    return width


def deer(d, center, scale=1, color=GREEN):
    x, y = center
    paths = [
        [(-21, -4), (-14, 16), (0, 27), (14, 16), (21, -4)],
        [(-18, 1), (-29, -17), (-30, -38)],
        [(-28, -20), (-45, -32), (-47, -45)],
        [(-30, -33), (-17, -45), (-17, -55)],
        [(18, 1), (29, -17), (30, -38)],
        [(28, -20), (45, -32), (47, -45)],
        [(30, -33), (17, -45), (17, -55)],
    ]
    for pts in paths:
        d.line([(int(x + px * scale), int(y + py * scale)) for px, py in pts], fill=color, width=max(2, int(3 * scale)), joint="curve")
    for ex in [-8, 8]:
        d.ellipse((x + ex * scale - 2, y + 5 * scale - 2, x + ex * scale + 2, y + 5 * scale + 2), fill=color)


def base(t):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    for x in range(0, W, 40):
        d.line((x, 0, x, H), fill="#102025")
    for y in range(0, H, 40):
        d.line((0, y, W, y), fill="#102025")
    deer(d, (73, 66), .43)
    text(d, (110, 37), "DeerMate", 28, WHITE, True)
    text(d, (110, 72), "A PRIVATE AGENT SECRETARY", 14, MUTED)
    pill(d, (950, 43), "DESIGN PREVIEW", GOLD, "#3d3424")
    d.line((48, 634, 1232, 634), fill=LINE)
    text(d, (50, 654), "CONCEPT FILM  /  SIMULATED DATA  /  NOT A LIVE DEMO", 16, MUTED)
    text(d, (1000, 654), "PYTHON FIRST", 16, GREEN, True)
    d.rectangle((0, H - 4, int(W * min(1, t / SECONDS)), H), fill=GREEN)
    return im, d


def title(d, kicker, heading, subtitle=None):
    text(d, (64, 132), kicker, 16, GREEN, True)
    text(d, (64, 166), heading, 44, WHITE, True)
    if subtitle:
        text(d, (66, 224), subtitle, 20, MUTED)


def frame(t):
    im, d = base(t)
    scene = min(5, int(t // 4))
    phase = (t % 4) / 4
    if scene == 0:
        pill(d, (65, 145), "MEET YOUR NEXT TEAMMATE")
        text(d, (64, 206), "One private assistant.", 62, WHITE, True)
        text(d, (64, 286), "Your agents. Your machines.", 56, GREEN, True)
        wrap(d, (68, 383), "Tell your secretary the goal. Let specialists take the work, and bring the evidence back to you.", 760, 28, MUTED)
        deer(d, (1070, 350), 2.0)
        pill(d, (68, 522), "DEERFLOW")
        pill(d, (213, 522), "PYTHON WORKER")
        pill(d, (406, 522), "SELF-HOSTED GOAL")
    elif scene == 1:
        title(d, "01 / ASK ONCE", "A goal, in your own words.", "A single conversation for the work you want done.")
        box(d, (65, 286, 1215, 432))
        text(d, (92, 309), "YOU", 16, GREEN, True)
        wrap(d, (92, 345), "Watch the repo. Design a fix, implement it on my home machine, then ask a separate agent to review the patch.", 1050, 28)
        box(d, (65, 454, 1215, 588), "#183029")
        text(d, (92, 476), "DEERMATE  /  INTENDED HANDOFF", 16, GREEN, True)
        wrap(d, (92, 513), "Design -> implementation -> independent review. Keep the result and execution evidence attached to the task.", 1050, 24, MUTED)
    elif scene == 2:
        title(d, "02 / ROUTE BY ROLE", "The right specialist for each step.", "Eligibility and project permissions come before model choice.")
        rows = [("01", "DESIGN", "Claude Code", "A bounded proposal"), ("02", "IMPLEMENT", "Codex", "Patch + test evidence"), ("03", "EXECUTE", "DSH / Qoder", "Scoped project work"), ("04", "REVIEW", "Separate session", "Fresh-context assessment")]
        for i, (n, role, agent, desc) in enumerate(rows):
            y = 286 + i * 75
            active = i == int(phase * 4) % 4
            box(d, (65, y, 1215, y + 63), "#203c32" if active else PANEL)
            text(d, (88, y + 19), n, 22, GREEN, True)
            text(d, (151, y + 20), role, 18, MUTED, True)
            text(d, (380, y + 17), agent, 24, WHITE, True)
            text(d, (790, y + 20), desc, 20, MUTED)
    elif scene == 3:
        title(d, "03 / YOUR OWN MACHINES", "Work travels. Authority stays explicit.", "Proposed Python worker + encrypted SSH transport.")
        nodes = [(65, "SECRETARY", "DeerFlow", "Plan and delegate"), (470, "PRIVATE LINK", "Python + SSH", "Verify host identity"), (875, "HOME WORKER", "Your machine", "Run a bounded task")]
        for x, label, name, detail in nodes:
            box(d, (x, 300, x + 340, 496))
            text(d, (x + 24, 326), label, 16, GREEN, True)
            text(d, (x + 24, 378), name, 30, WHITE, True)
            text(d, (x + 24, 439), detail, 20, MUTED)
        for x in [405, 810]:
            d.line((x + 9, 397, x + 54, 397), fill=GREEN, width=2)
            d.polygon([(x + 54, 397), (x + 45, 391), (x + 45, 403)], fill=GREEN)
        gap = 414 if phase < .5 else 819
        dot = gap + int((phase * 2 % 1) * 39)
        d.ellipse((dot - 5, 392, dot + 5, 402), fill=WHITE)
        text(d, (67, 546), "Default: Python-owned services. Hermesh: optional external bridge.", 22, MUTED)
    elif scene == 4:
        title(d, "04 / ONE PLACE TO FOLLOW", "A workbench for your agent team.", "Concept layout. Example tasks and states are simulated.")
        box(d, (65, 283, 1215, 593))
        text(d, (88, 304), "TASK", 16, MUTED, True)
        text(d, (600, 304), "ASSIGNEE", 16, MUTED, True)
        text(d, (891, 304), "STATE", 16, MUTED, True)
        rows = [("Prepare login fix", "Codex / home", "RUNNING", GREEN), ("Review checkout patch", "Review agent", "QUEUED", GOLD), ("Compare release notes", "Research agent", "COMPLETE", GREEN)]
        for i, (task, who, state, color) in enumerate(rows):
            y = 354 + i * 74
            d.line((88, y - 13, 1190, y - 13), fill=LINE)
            text(d, (88, y + 5), task, 24, WHITE, True)
            text(d, (600, y + 8), who, 20, MUTED)
            pill(d, (889, y + 2), state, color, "#24352f")
        text(d, (88, 567), "Inspect events   /   Read artifacts   /   Interrupt   /   Continue", 16, MUTED)
    else:
        title(d, "05 / BRING BACK EVIDENCE", "A result you can actually inspect.", "The target: diffs, test receipts, sources, and explicit uncertainty.")
        cards = [(65, "DIFF", "What changed", "An isolated patch"), (455, "TESTS", "What ran", "Captured execution output"), (845, "SOURCES", "What supports it", "Traceable references")]
        for x, label, name, desc in cards:
            box(d, (x, 288, x + 370, 470))
            text(d, (x + 24, 313), label, 16, GREEN, True)
            text(d, (x + 24, 361), name, 28, WHITE, True)
            text(d, (x + 24, 420), desc, 18, MUTED)
        text(d, (67, 508), "Now: public design preview. Next: one working local task.", 24, WHITE, True)
        text(d, (67, 555), "github.com/mzydmer/deermate", 24, GREEN)
    return im


def hero():
    im = Image.new("RGB", (1600, 650), "#edf2e8")
    d = ImageDraw.Draw(im)
    text(d, (76, 58), "DEERMATE", 20, "#2d6553", True)
    text(d, (74, 116), "One private assistant.", 74, "#102e2a", True)
    text(d, (74, 210), "Your agents. Your machines.", 62, "#306953", True)
    wrap(d, (79, 314), "An open-source secretary for delegating real work across your agent team.", 1000, 28, "#52665c")
    for x, label in [(80, "PYTHON BACKEND PLAN"), (359, "BUILT AROUND DEERFLOW"), (672, "DESIGN PREVIEW")]:
        pill(d, (x, 426), label, "#1d5e43", "#d5e7d5")
    deer(d, (1350, 246), 2.7, "#306953")
    d.line((80, 516, 1520, 516), fill="#ccd8cb", width=2)
    text(d, (80, 551), "TALK TO YOUR SECRETARY", 18, "#52665c", True)
    text(d, (592, 551), "DELEGATE WITH BOUNDARIES", 18, "#52665c", True)
    text(d, (1142, 551), "FOLLOW THE EVIDENCE", 18, "#52665c", True)
    im.save(OUT / "hero.png", optimize=True)


def render(skip_video=False):
    OUT.mkdir(parents=True, exist_ok=True)
    hero()
    frame(17.7).save(OUT / "concept-poster.png", optimize=True)
    contact = Image.new("RGB", (1280, 1080), BG)
    for i in range(6):
        contact.paste(frame(i * 4 + 1.5).resize((640, 360), Image.Resampling.LANCZOS), ((i % 2) * 640, (i // 2) * 360))
    contact.save(OUT / "storyboard.png", optimize=True)
    frames = [frame(i * .5).resize((768, 432), Image.Resampling.LANCZOS).quantize(colors=96) for i in range(48)]
    frames[0].save(OUT / "concept-preview.gif", save_all=True, append_images=frames[1:], duration=500, loop=0, optimize=True)
    if not skip_video:
        import imageio_ffmpeg
        writer = imageio_ffmpeg.write_frames(str(OUT / "deermate-concept.mp4"), (W, H), fps=FPS, codec="libx264", pix_fmt_in="rgb24", pix_fmt_out="yuv420p", quality=8, macro_block_size=1, output_params=["-movflags", "+faststart"])
        writer.send(None)
        try:
            for i in range(FPS * SECONDS):
                writer.send(frame(i / FPS).tobytes())
        finally:
            writer.close()
        verify = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(OUT / "deermate-concept.mp4"), "-f", "null", "-"], capture_output=True, text=True)
        if verify.returncode:
            raise RuntimeError(verify.stderr)
    for p in sorted(OUT.iterdir()):
        print(f"{p.relative_to(ROOT)}  {p.stat().st_size:,} bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-video", action="store_true")
    render(parser.parse_args().skip_video)
