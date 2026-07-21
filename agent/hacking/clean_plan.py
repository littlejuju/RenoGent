#!/usr/bin/env python3
"""Build-wall round handback plan (干净底图) — generic renderer.

Whitens the hack_plan's removed_segments on the plan image, draws my SUGGESTED
built_segments as very light gray double lines with circled labels, and appends
a caption strip. The user decides: accept suggestions / hand-draw own segments /
no wall. Regulation-tier (red) captions mean the enclosure MUST exist in some
form — the user may redraw the enclosure line but cannot drop it.

captions.json: [{"tier": "suggest"|"red", "text": "..."}, ...]
Usage:
  python3 clean_plan.py --plan hack_plan.json --image floorplan-src.png \
      --out clean.png --captions captions.json [--crop x0,y0,x1,y1]
Note: use a CJK-capable font; ✓/emoji glyphs render as tofu — use plain text.
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
LINE, FILL, LABEL = (200, 200, 200), (238, 238, 238), (150, 150, 150)
CIRCLED = "①②③④⑤⑥⑦⑧⑨"


def font(size):
    for f in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--captions", required=True)
    ap.add_argument("--crop")
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text())
    caps = json.loads(Path(a.captions).read_text())
    img = cv2.imread(a.image, cv2.IMREAD_COLOR)
    for seg in plan["removed_segments"]:
        x0, y0, x1, y1 = seg["rect"]
        img[y0:y1, x0:x1] = 255
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    dr = ImageDraw.Draw(pil)
    f_label = font(26)
    for i, seg in enumerate(plan.get("built_segments", [])):
        x0, y0, x1, y1 = seg["rect"]
        dr.rectangle([x0, y0, x1 - 1, y1 - 1], fill=FILL)
        if (x1 - x0) >= (y1 - y0):
            dr.rectangle([x0, y0, x1 - 1, y0 + 1], fill=LINE)
            dr.rectangle([x0, y1 - 2, x1 - 1, y1 - 1], fill=LINE)
            lx, ly = (x0 + x1) // 2 - 13, y1 + 6
        else:
            dr.rectangle([x0, y0, x0 + 1, y1 - 1], fill=LINE)
            dr.rectangle([x1 - 2, y0, x1 - 1, y1 - 1], fill=LINE)
            lx, ly = x1 + 6, (y0 + y1) // 2 - 13
        dr.text((lx, ly), CIRCLED[i], font=f_label, fill=LABEL)
    if a.crop:
        pil = pil.crop([int(v) for v in a.crop.split(",")])
    f_cap = font(22)
    pad, lh = 18, 32
    W, H = pil.size
    canvas = Image.new("RGB", (W, H + pad * 2 + lh * len(caps)), (255, 255, 255))
    canvas.paste(pil, (0, 0))
    dc = ImageDraw.Draw(canvas)
    dc.line([(0, H + 1), (W, H + 1)], fill=(225, 225, 225), width=1)
    for j, c in enumerate(caps):
        color = (196, 46, 46) if c.get("tier") == "red" else (105, 105, 105)
        dc.text((pad, H + pad + j * lh), c["text"], font=f_cap, fill=color)
    canvas.save(a.out)
    print(f"{a.out}: {canvas.size}, suggestions={len(plan.get('built_segments', []))}")


if __name__ == "__main__":
    main()
