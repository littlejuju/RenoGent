#!/usr/bin/env python3
"""Local quarantine hook for Living/Dining render candidates.

This hook is intentionally conservative. It does not certify final design
quality; it blocks obvious candidates before they can be promoted to any
human-facing surface:

- visible window grid / horizontal bars
- missing same-wall bright door+window composition
- suspicious side-wall glazed door panel

Final pass still requires homeowner approval.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image


def runs(values, min_len=3):
    out = []
    start = None
    for i, v in enumerate(values):
        if v and start is None:
            start = i
        if (not v or i == len(values) - 1) and start is not None:
            end = i if not v else i + 1
            if end - start >= min_len:
                out.append((start, end))
            start = None
    return out


def fail(path: Path, element: str, evidence: str) -> dict:
    return {
        "path": str(path),
        "pass": False,
        "violations": [{"element": element, "evidence": evidence}],
        "measurements": {},
    }


def audit(path: Path) -> dict:
    if not path.exists():
        return fail(path, "file-missing", "Render file does not exist.")

    im = Image.open(path).convert("L")
    w0, h0 = im.size
    target_w = 420
    target_h = round(h0 * target_w / w0)
    im = im.resize((target_w, target_h))
    w, h = im.size
    pix = im.load()

    # Candidate far-wall search area: central 20%-75% height, not ceiling/floor.
    y0, y1 = int(h * 0.22), int(h * 0.72)
    x0, x1 = int(w * 0.08), int(w * 0.92)

    # HDB window glass often renders as off-white. A too-high threshold only
    # catches tiny transom highlights and misses bars.
    bright = 190
    row_bright = []
    for y in range(y0, y1):
        count = sum(1 for x in range(x0, x1) if pix[x, y] >= bright)
        row_bright.append(count / (x1 - x0) > 0.15)
    row_runs = runs(row_bright, min_len=10)
    if not row_runs:
        return fail(path, "same_wall_missing", "No broad bright far-wall window/door band detected.")
    wr = max(row_runs, key=lambda r: r[1] - r[0])
    wy0, wy1 = y0 + wr[0], y0 + wr[1]

    col_bright = []
    for x in range(x0, x1):
        count = sum(1 for y in range(wy0, wy1) if pix[x, y] >= bright)
        col_bright.append(count / max(1, (wy1 - wy0)) > 0.10)
    col_runs = runs(col_bright, min_len=8)
    if not col_runs:
        return fail(path, "same_wall_missing", "No continuous bright window/door columns detected.")
    wx0 = x0 + min(r[0] for r in col_runs)
    wx1 = x0 + max(r[1] for r in col_runs)

    band_w = max(1, wx1 - wx0)
    band_h = max(1, wy1 - wy0)

    # Window grids / horizontal bars: many dark rows or columns crossing the
    # bright band indicate generated grille/muntin artifacts.
    h_flags = []
    for y in range(wy0 + 3, wy1 - 3):
        dark = sum(1 for x in range(wx0, wx1) if pix[x, y] < 178)
        h_flags.append(dark / band_w > 0.20)
    horizontal_bars = len(runs(h_flags, min_len=1))
    horizontal_rows = sum(1 for flag in h_flags if flag)
    horizontal_row_ratio = horizontal_rows / max(1, band_h)

    vertical_flags = []
    for x in range(wx0 + 3, wx1 - 3):
        dark = sum(1 for y in range(wy0, wy1) if pix[x, y] < 178)
        vertical_flags.append(dark / band_h > 0.35)
    vertical_bars = len(runs(vertical_flags, min_len=1))

    violations = []
    if horizontal_bars >= 5 or horizontal_row_ratio > 0.12:
        violations.append(
            {
                "element": "window_grid",
                "evidence": (
                    f"Detected {horizontal_rows} dark horizontal scan rows "
                    f"({horizontal_row_ratio:.1%} of the bright band) across "
                    f"{horizontal_bars} compressed bar groups."
                ),
            }
        )
    if vertical_bars >= 10:
        violations.append(
            {
                "element": "window_grid",
                "evidence": f"Detected {vertical_bars} vertical dark bars, likely multi-pane grid/grille.",
            }
        )

    # Same-wall composition: the bright band should span a meaningful width and
    # include a door-like bright zone next to the window zone, not a tiny window.
    if band_w < w * 0.35:
        violations.append(
            {
                "element": "same_wall_composition",
                "evidence": "Bright window/door band is too narrow to represent same-wall bi-fold door + window.",
            }
        )

    # Side-wall glazed-door suspicion: large bright rectangle in the left third,
    # lower-middle, separated from the main far-wall band.
    left_x0, left_x1 = int(w * 0.05), int(w * 0.34)
    side_y0, side_y1 = int(h * 0.34), int(h * 0.72)
    side_bright = sum(
        1 for y in range(side_y0, side_y1) for x in range(left_x0, left_x1) if pix[x, y] >= 205
    )
    side_area = (left_x1 - left_x0) * (side_y1 - side_y0)
    far_overlaps_left = wx0 < left_x1 and wy0 < side_y1 and wy1 > side_y0
    if side_bright / side_area > 0.24 and not far_overlaps_left:
        violations.append(
            {
                "element": "side_wall_glazed_door",
                "evidence": "Large bright glazed rectangle detected on left side wall, not coplanar with the main window band.",
            }
        )

    return {
        "path": str(path),
        "pass": not violations,
        "violations": violations,
        "measurements": {
            "image_size": [w0, h0],
            "window_band_box_resized": [wx0, wy0, wx1, wy1],
            "horizontal_bars": horizontal_bars,
            "horizontal_row_ratio": round(horizontal_row_ratio, 3),
            "vertical_bars": vertical_bars,
            "band_width_ratio": round(band_w / w, 3),
        },
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: living_dining.py <render-image>", file=sys.stderr)
        return 2
    result = audit(Path(argv[1]))
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
