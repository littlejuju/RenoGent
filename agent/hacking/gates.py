#!/usr/bin/env python3
"""G1-G5 hacking validity gates (generic, productized from pj-audit-0717).

Input: a hack_plan.json + the source plan image. Applies the surgical edit
(white out removed_segments, draw built_segments as double lines) and validates:
  G1 removed rects contain only thin partition ink (no >=6x6-erosion-surviving RC)
  G2 edit is surgical: pixel-equal outside declared rects (windows can't move)
  G3 column detection identical before/after (11x11 window, >=109 dark)
  G4 kept door/jamb planes zero-intersect removal rects
  G5 interface maximal: declared interface_zones keep only RC; leftover ink <=60px

hack_plan.json schema (per plan): removed_segments[{rect,wall,run_mm}],
built_segments[{rect,wall,run_mm,wall_type?}], doors_preserved[[x0,y0,x1,y1]],
interface_zones[[x0,y0,x1,y1]], kept, goal, note.

Usage:
  python3 gates.py --plan hack_plan.json --image floorplan.png \
      --out hacked.png [--color-image floorplan-src.png --color-out hacked-src.png] \
      --scan 150,660,800,1200 [--report validation.txt]
Exit 0 = all gates pass.
"""
import argparse
import json
import sys
from pathlib import Path
import numpy as np
import cv2


def col_detect(gray, scan):
    dark = (gray < 80).astype(int)
    H, W = gray.shape
    I = np.zeros((H + 1, W + 1), int)
    I[1:, 1:] = np.cumsum(np.cumsum(dark, 0), 1)

    def bs(y0, x0, y1, x1):
        return I[y1, x1] - I[y0, x1] - I[y1, x0] + I[y0, x0]

    pts = set()
    for y in range(scan[1], min(scan[3], H - 6), 2):
        for x in range(scan[0], min(scan[2], W - 6), 2):
            if bs(y - 5, x - 5, y + 6, x + 6) >= 121 * 0.9:
                pts.add((x, y))
    return pts


def apply_edit(src, plan, color=False):
    out = src.copy()
    white = 255 if not color else (255, 255, 255)
    for seg in plan["removed_segments"]:
        x0, y0, x1, y1 = seg["rect"]
        out[y0:y1, x0:x1] = white
    for seg in plan.get("built_segments", []):
        x0, y0, x1, y1 = seg["rect"]
        ink = 30 if not color else (30, 30, 30)
        if (x1 - x0) >= (y1 - y0):
            out[y0:y0 + 2, x0:x1] = ink
            out[y1 - 2:y1, x0:x1] = ink
        else:
            out[y0:y1, x0:x0 + 2] = ink
            out[y0:y1, x1 - 2:x1] = ink
    return out


def validate(plan, src, hacked, scan):
    report, ok = [], True
    for seg in plan["removed_segments"]:
        x0, y0, x1, y1 = seg["rect"]
        zone = (src[y0:y1, x0:x1] < 110).astype(np.uint8)
        solid = int(cv2.erode(zone, np.ones((6, 6), np.uint8)).sum())
        g = solid == 0
        ok &= g
        report.append(f"G1 {'PASS' if g else 'FAIL'} rect {seg['rect']}: solid px={solid} — {seg['wall']}")
    mask = np.ones_like(src, bool)
    for seg in plan["removed_segments"] + plan.get("built_segments", []):
        x0, y0, x1, y1 = seg["rect"]
        mask[y0:y1, x0:x1] = False
    g2 = bool(np.array_equal(src[mask], hacked[mask]))
    ok &= g2
    report.append(f"G2 {'PASS' if g2 else 'FAIL'}: surgical (pixel-equal outside declared rects)")
    g3 = col_detect(src, scan) == col_detect(hacked, scan)
    ok &= g3
    report.append(f"G3 {'PASS' if g3 else 'FAIL'}: column detection unchanged")
    for iz in plan.get("interface_zones", []):
        x0, y0, x1, y1 = iz
        zone = (hacked[y0:y1, x0:x1] < 110).astype(np.uint8)
        rc = cv2.dilate(cv2.erode(zone, np.ones((6, 6), np.uint8)), np.ones((10, 10), np.uint8))
        leftover = int((zone & (1 - rc)).sum())
        g = leftover <= 60
        ok &= g
        report.append(f"G5 {'PASS' if g else 'FAIL'} interface {iz}: leftover non-RC ink {leftover}px (<=60)")
    g4 = True
    for d in plan.get("doors_preserved", []):
        for seg in plan["removed_segments"]:
            r = seg["rect"]
            if not (d[2] <= r[0] or d[0] >= r[2] or d[3] <= r[1] or d[1] >= r[3]):
                g4 = False
    ok &= g4
    report.append(f"G4 {'PASS' if g4 else 'FAIL'}: kept doors zero-intersect removal rects")
    report.append("=> ALL GATES PASS" if ok else "=> GATE FAILED")
    return ok, "\n".join(report)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--color-image")
    ap.add_argument("--color-out")
    ap.add_argument("--scan", required=True, help="x0,y0,x1,y1 column-scan window")
    ap.add_argument("--report")
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text())
    scan = [int(v) for v in a.scan.split(",")]
    src = cv2.imread(a.image, cv2.IMREAD_GRAYSCALE)
    hacked = apply_edit(src, plan)
    cv2.imwrite(a.out, hacked)
    if a.color_image and a.color_out:
        csrc = cv2.imread(a.color_image)
        cv2.imwrite(a.color_out, apply_edit(csrc, plan, color=True))
    ok, rep = validate(plan, src, hacked, scan)
    if a.report:
        Path(a.report).write_text(rep)
    print(rep)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
