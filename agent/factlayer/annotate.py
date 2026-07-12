#!/usr/bin/env python3
"""Draw a camera marker on a floor plan: red dot = where you stand,
arrow + translucent view cone = where you look. Sent with every render so the
homeowner (and the audit hook) can verify the viewpoint against the plan.

Usage: annotate.py <plan> <out> <cam_x> <cam_y> <look_x> <look_y> <label>
"""
import math
import sys

from PIL import Image, ImageDraw, ImageFont


def annotate(plan, out, cx, cy, lx, ly, label):
    im = Image.open(plan).convert("RGBA")
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    ang = math.atan2(ly - cy, lx - cx)
    cone_len = max(120, math.hypot(lx - cx, ly - cy) * 0.9)
    spread = math.radians(28)
    p1 = (cx + cone_len * math.cos(ang - spread), cy + cone_len * math.sin(ang - spread))
    p2 = (cx + cone_len * math.cos(ang + spread), cy + cone_len * math.sin(ang + spread))
    d.polygon([(cx, cy), p1, p2], fill=(255, 60, 60, 60))

    ah = (cx + cone_len * 0.75 * math.cos(ang), cy + cone_len * 0.75 * math.sin(ang))
    d.line([(cx, cy), ah], fill=(220, 30, 30, 230), width=6)
    for s in (+1, -1):  # arrowhead
        wing = (ah[0] - 24 * math.cos(ang - s * 0.5), ah[1] - 24 * math.sin(ang - s * 0.5))
        d.line([ah, wing], fill=(220, 30, 30, 230), width=6)

    r = 14
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(220, 30, 30, 255), outline=(255, 255, 255, 255), width=3)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 34)
    except Exception:
        font = ImageFont.load_default()
    tx, ty = cx + 20, cy - 52
    bbox = d.textbbox((tx, ty), label, font=font)
    d.rectangle([bbox[0] - 8, bbox[1] - 6, bbox[2] + 8, bbox[3] + 6], fill=(255, 255, 255, 235), outline=(220, 30, 30, 255), width=2)
    d.text((tx, ty), label, fill=(180, 20, 20, 255), font=font)

    final = Image.alpha_composite(im, overlay).convert("RGB")

    # crop away phone-screenshot chrome (same density scan as render.preprocess):
    # WhatsApp previews a tall screenshot by its blank bottom half, so the marker
    # is invisible unless we crop to the actual drawing
    w, h = final.size
    px = final.convert("L").point(lambda p: 1 if p > 200 else 0).load()
    rows = [y for y in range(h) if sum(px[x, y] for x in range(0, w, 4)) * 4 > 0.5 * w]
    if rows:
        y0, y1 = rows[0], rows[-1]
        # tighten: drop leading/trailing blank rows (all-white, no drawing ink)
        inked = [y for y in range(y0, y1) if sum(px[x, y] for x in range(0, w, 4)) * 4 < 0.99 * w]
        if inked:
            y0, y1 = max(y0, inked[0] - 20), min(y1, inked[-1] + 20)
        cols = [x for x in range(w) if sum(px[x, y] for y in range(y0, y1, 4)) * 4 > 0.5 * (y1 - y0)]
        if cols:
            x0, x1 = cols[0], cols[-1]
            area = (x1 - x0) * (y1 - y0)
            if 0.20 * w * h <= area <= 0.95 * w * h:
                pad = 8
                final = final.crop((max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad)))

    final.save(out, "JPEG", quality=90)
    print(f"annotated -> {out}")


if __name__ == "__main__":
    annotate(sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]),
             float(sys.argv[5]), float(sys.argv[6]), sys.argv[7])
