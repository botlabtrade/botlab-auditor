"""Generate submission/cover.png (1280x720) with PIL - text and simple shapes only, no assets.

    python submission/make_cover.py

Re-run it after editing; it overwrites cover.png in place.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cover.png")

BG = (14, 17, 22)
PANEL = (22, 26, 33)
LINE = (38, 44, 54)
INK = (231, 234, 239)
MUTED = (153, 163, 177)
GREEN = (47, 189, 140)
GREEN_DIM = (15, 38, 32)
RED = (255, 143, 156)
RED_DIM = (42, 20, 25)
AMBER = (240, 193, 115)

# Font candidates: a Windows set, a Linux set, then PIL's built-in bitmap font.
SANS = ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"]
SANS_BOLD = ["arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]
MONO = ["consola.ttf", "DejaVuSansMono.ttf", "LiberationMono-Regular.ttf"]
MONO_BOLD = ["consolab.ttf", "DejaVuSansMono-Bold.ttf", "LiberationMono-Bold.ttf"]


def font(names, size):
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def pill(d, box, fill, outline, radius=999):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=1)


def main() -> str:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    f_kicker = font(SANS_BOLD, 20)
    f_title = font(SANS_BOLD, 62)
    f_sub = font(SANS, 25)
    f_small = font(SANS, 19)
    f_tiny = font(SANS, 16)
    f_mono = font(MONO, 18)
    f_mono_b = font(MONO_BOLD, 20)
    f_badge = font(SANS_BOLD, 17)

    # A thin accent rule down the left edge.
    d.rectangle([0, 0, 7, H], fill=GREEN)

    # ------------------------------------------------------------------ left column: the pitch
    x = 54
    d.ellipse([x, 60, x + 15, 75], fill=GREEN)
    d.text((x + 28, 57), "BOTLAB AUDITOR", font=f_kicker, fill=INK)
    bx = x + 28 + int(d.textlength("BOTLAB AUDITOR", font=f_kicker)) + 22
    bw = int(d.textlength("BLAST RADIUS ZERO", font=f_tiny)) + 30
    pill(d, (bx, 54, bx + bw, 82), GREEN_DIM, GREEN)
    d.text((bx + 15, 60), "BLAST RADIUS ZERO", font=f_tiny, fill=GREEN)

    d.text((x, 126), "Runs a stranger's", font=f_title, fill=INK)
    d.text((x, 196), "trading strategy.", font=f_title, fill=INK)
    d.text((x, 266), "Finds the lie.", font=f_title, fill=GREEN)
    d.text((x, 336), "Cannot be hurt by it.", font=f_title, fill=INK)

    d.line([x, 432, x + 580, 432], fill=LINE, width=1)
    d.text((x, 452), "Look-ahead bias  -  overfitting  -  real costs  -  hostile code,",
           font=f_sub, fill=MUTED)
    d.text((x, 484), "contained in a two-layer sandbox and reported as a finding.",
           font=f_sub, fill=MUTED)

    # Verdict chips: the four demo outcomes.
    chips = [("WATCH", GREEN, GREEN_DIM), ("NOT_READY", AMBER, (42, 34, 20)),
             ("REJECTED_LOOKAHEAD", RED, RED_DIM), ("REJECTED_UNSAFE", RED, RED_DIM)]
    cx, cy = x, 522
    for label, col, bg in chips:
        w = int(d.textlength(label, font=f_badge)) + 26
        if cx + w > x + 620:                      # wrap to a second row
            cx, cy = x, cy + 42
        pill(d, (cx, cy, cx + w, cy + 34), bg, col, radius=8)
        d.text((cx + 13, cy + 7), label, font=f_badge, fill=col)
        cx += w + 10

    d.text((x, 620), "Vultr Cloud Compute VM  +  Vultr Serverless Inference", font=f_small,
           fill=INK)
    d.text((x, 648), "MIT licensed  -  github.com/botlabtrade/botlab-auditor", font=f_small,
           fill=MUTED)
    d.text((x, 676), "A passing audit is a reason to forward-test small, never a promise of profit.",
           font=f_tiny, fill=MUTED)

    # ----------------------------------------------- right column: the sandbox-events panel
    px0, py0, px1, py1 = 760, 96, 1232, 624
    d.rounded_rectangle([px0, py0, px1, py1], radius=14, fill=PANEL, outline=LINE, width=1)
    d.text((px0 + 24, py0 + 22), "SANDBOX EVENTS", font=f_kicker, fill=INK)
    d.text((px0 + 24, py0 + 52), "every refusal, with the rule that refused it", font=f_tiny,
           fill=MUTED)
    bw2 = int(d.textlength("12 BLOCKED", font=f_badge)) + 28
    pill(d, (px1 - 24 - bw2, py0 + 20, px1 - 24, py0 + 50), RED_DIM, RED, radius=8)
    d.text((px1 - 24 - bw2 + 14, py0 + 26), "12 BLOCKED", font=f_badge, fill=RED)

    rows = [
        ("os.system", "shell command refused"),
        ("subprocess.Popen", "process launch refused"),
        ("socket.getaddrinfo", "network refused"),
        ("socket.connect", "network refused"),
        ("open", "write outside scratch dir"),
        ("wall_clock_timeout", "infinite loop killed"),
    ]
    y = py0 + 96
    for call, why in rows:
        d.rounded_rectangle([px0 + 20, y, px1 - 20, y + 52], radius=8, fill=RED_DIM,
                            outline=RED, width=1)
        d.rectangle([px0 + 20, y, px0 + 24, y + 52], fill=RED)
        d.text((px0 + 38, y + 7), call, font=f_mono_b, fill=RED)
        d.text((px0 + 38, y + 29), why, font=f_mono, fill=MUTED)
        y += 62

    d.text((px0 + 24, py1 - 40), "0 trades  -  host untouched  -  audit continued",
           font=f_small, fill=GREEN)

    img.save(OUT, "PNG", optimize=True)
    return OUT


if __name__ == "__main__":
    print(main())
