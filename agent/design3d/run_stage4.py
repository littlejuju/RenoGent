#!/usr/bin/env python3
"""Stage 4b — nano-banana stylization of the audited Cycles base renders.

Uses the locked recipe in agent/factlayer/render.py (structure lock + HDB typology).
P1 (user 2026-07-22): dark walnut floor; warm off-white walls + under-window
cabinets; light walnut closet joinery; walk-in closet; full-length light-coffee
blackout + sheer curtains; NO ceiling light, floor lamp only. AC compressor sits
outside the BR1 window; wall FCU + trunking already in the base geometry.

Usage: python3 run_stage4.py <out_root> [cam ...]   (default: all three cams)
Optional per-cam fix: python3 run_stage4.py <out_root> cam-entry --fix "instruction" --round 2
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "factlayer"))
from render import render  # noqa: E402

STYLE = (
    "Transform this into a photorealistic interior photo of the SAME room, same camera. "
    "This is the master bedroom of a Singapore HDB flat (two bedrooms merged into one suite). "
    "Keep every wall, window opening, door opening, column, ceiling height and every piece of "
    "furniture in EXACTLY the position shown; do not add, remove, move or resize any of them. "
    "Finishes: dark walnut wood plank flooring; warm off-white painted walls and flat ceiling; "
    "low under-window cabinetry in warm off-white with a thin wood top; walk-in closet units, "
    "pocket wardrobe and bed headboard in light walnut matte wood; bed with ivory linen bedding; "
    "full-height light coffee (latte) blackout curtains hanging stacked at the window edges, plus "
    "white translucent sheer curtains drawn across the windows, both floor-to-ceiling length; "
    "a slim brass floor lamp glowing warm white — it is the ONLY artificial light: absolutely no "
    "ceiling lamp, no pendant, no chandelier, no downlights, no cove lighting, flat plain ceiling; "
    "the white wall-mounted split air-conditioner indoor unit is recessed in the wall niche above the "
    "tall walnut cabinet and stays exactly where shown — never anywhere else, never above doors; "
    "soft tropical daylight, realistic shadows, professional interior photography."
)

CAMS = {
    "cam-entry": "Camera stands at the room's entrance door looking north-east: the wide window with sheer "
                 "curtain on the LEFT, then a full-height wall niche holding a tall light-walnut cabinet with "
                 "the white air-con unit recessed above it, and the bed with its headboard on the right wall.",
    "cam-ne": "Camera stands in the north-east corner looking south-west: the light walnut walk-in "
              "closet corner ahead, the entrance door on the left, big window with sheer curtain on the right.",
    "cam-br3": "Camera stands by the north-west window looking south-east: bed on the left, glowing "
               "floor lamp beside it, open entrance door and light walnut pocket wardrobe ahead.",
}

if __name__ == "__main__":
    OUT = pathlib.Path(sys.argv[1])
    args = sys.argv[2:]
    fix = ""
    rnd = 1
    if "--fix" in args:
        i = args.index("--fix"); fix = args[i + 1]; args = args[:i] + args[i + 2:]
    if "--round" in args:
        i = args.index("--round"); rnd = int(args[i + 1]); args = args[:i] + args[i + 2:]
    cams = args or list(CAMS)

    for cid in cams:
        if rnd == 1:
            src = OUT / "renders/stage4-base" / f"{cid}-base.png"
        else:
            src = OUT / "renders/stage4-design" / f"{cid}-design-r{rnd - 1}.png"
        dst = OUT / "renders/stage4-design" / f"{cid}-design-r{rnd}.png"
        dst.parent.mkdir(exist_ok=True)
        instr = CAMS[cid] + (" " + fix if fix else "")
        print(f"[{cid}] round {rnd} -> {dst.name}")
        render(str(src), str(dst), style=STYLE, edit_instruction=instr)
        print(f"[{cid}] done")
