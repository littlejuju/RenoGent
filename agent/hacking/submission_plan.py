#!/usr/bin/env python3
"""HDB renovation-permit style plan (定稿报批图) — generic renderer.

HDB colour code (see hacking_rules.json:submission-drawing-convention):
  RED    = wall/door to be demolished
  BLUE   = new wall to be erected
  YELLOW = demolish + erect new wall at the SAME location
Rendered as translucent overlays on the ORIGINAL plan (walls not whited out),
with legend + notes strip. YELLOW is auto-detected: a built rect intersecting
any removal rect = same-location rebuild.

notes.json: {"title": "...", "notes": ["line1", ...]}
Usage:
  python3 submission_plan.py --plan hack_plan.json --image floorplan-src.png \
      --out submission.png --notes notes.json [--crop x0,y0,x1,y1]
"""
import argparse
import json
from pathlib import Path
import cv2
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]
RED, BLUE, YELLOW = (214, 40, 40), (35, 80, 210), (232, 185, 15)


def font(size):
    for f in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def overlap(a, b):
    return not (a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--notes", required=True)
    ap.add_argument("--crop")
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text())
    meta = json.loads(Path(a.notes).read_text())
    img = cv2.imread(a.image, cv2.IMREAD_COLOR)
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).convert("RGBA")
    ov = Image.new("RGBA", pil.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)
    removed = [s["rect"] for s in plan["removed_segments"]]
    built = [s["rect"] for s in plan.get("built_segments", [])]
    yellow = [r for r in built if any(overlap(r, q) for q in removed)]
    for r in removed:
        dr.rectangle([r[0], r[1], r[2] - 1, r[3] - 1], fill=RED + (95,), outline=RED + (220,))
    for r in built:
        c = YELLOW if r in yellow else BLUE
        dr.rectangle([r[0], r[1], r[2] - 1, r[3] - 1], fill=c + (140,), outline=c + (255,))
    pil = Image.alpha_composite(pil, ov).convert("RGB")
    if a.crop:
        pil = pil.crop([int(v) for v in a.crop.split(",")])
    f_t, f_l = font(24), font(20)
    W, H = pil.size
    legend = [(RED, "RED — WALL/DOOR TO BE DEMOLISHED"),
              (BLUE, "BLUE — NEW WALL TO BE ERECTED")]
    if yellow:
        legend.append((YELLOW, "YELLOW — DEMOLISH & REBUILD WALL AT SAME LOCATION"))
    pad, lh = 18, 30
    notes = meta.get("notes", [])
    canvas = Image.new("RGB", (W, H + pad * 3 + 34 + lh * (len(legend) + len(notes))), (255, 255, 255))
    canvas.paste(pil, (0, 0))
    dc = ImageDraw.Draw(canvas)
    dc.line([(0, H + 1), (W, H + 1)], fill=(220, 220, 220), width=1)
    y = H + pad
    dc.text((pad, y), meta.get("title", "PROPOSED RENOVATION PLAN"), font=f_t, fill=(40, 40, 40))
    y += 40
    for color, text in legend:
        dc.rectangle([pad, y + 4, pad + 34, y + 18], fill=color)
        dc.text((pad + 44, y), text, font=f_l, fill=(60, 60, 60))
        y += lh
    for line in notes:
        dc.text((pad, y), line, font=f_l, fill=(105, 105, 105))
        y += lh
    canvas.save(a.out)
    print(f"{a.out}: {canvas.size}, red={len(removed)} blue={len(built) - len(yellow)} yellow={len(yellow)}")


if __name__ == "__main__":
    main()
