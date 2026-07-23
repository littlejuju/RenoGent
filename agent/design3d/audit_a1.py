#!/usr/bin/env python3
"""A1 gate — stage-1 shell vs room_model. Deterministic.

  A1-1 required objects exist (floor/ceiling/2 glass/door flanks+header/parapet+caps)
  A1-2 bbox sanity: walls span z0..CEIL, ceiling above CEIL, floor below 0,
        glass inside window z, floor bbox == polygon bbox ±2mm
  A1-3 wall probes: every edge hit at ~300mm; window edges hit glass; door edge passes through
  A1-4 enclosure: 0 unexplained ray escapes
  A1-5 renders: 8 files exist, visual non-dark, ID pass contains expected class colors

Usage: python3 audit_a1.py <room_model.json> <out_root>
"""
import json, sys, pathlib
from PIL import Image
import numpy as np

M = json.load(open(sys.argv[1]))
OUT = pathlib.Path(sys.argv[2])
I = json.load(open(OUT / "audits" / "introspect_stage1.json"))
objs = I["objects"]
CEIL = M["ceiling_mm"]
R = []
def check(rule, ok, detail): R.append({"rule": rule, "pass": bool(ok), "detail": str(detail)})

req = ["floor", "ceiling", "glass-win-br1", "glass-win-br3",
       "wall-e08-seg0", "wall-e08-seg1", "wall-e08-header0",          # door edge
       "wall-e02-parapet0", "wall-e02-cap0l", "wall-e02-cap0r",       # br3 window + niche caps
       "wall-e02-parapet1", "wall-e02-cap1l", "wall-e02-cap1r",       # br1 window + its 324 niche caps
       "wall-e02-header0", "wall-e02-header1",
       "wall-e00"]                                                    # niche outer wall: SOLID (no window)
req += [r["id"] for r in M.get("risk_elements", [])]                  # risk volumes must be DRAWN, never silent
missing = [r for r in req if r not in objs]
riskbad = [(r["id"], objs[r["id"]]) for r in M.get("risk_elements", []) if r["id"] in objs
           and any(abs(g - w) > 2 for g, w in zip(objs[r["id"]]["min"] + objs[r["id"]]["max"],
                                                  r["box"][:3] + r["box"][3:]))]
check("A1-1 objects", not missing and not riskbad,
      f"missing={missing or 'none'} risk-off={riskbad or 'none'} total={len(objs)}")

bad = []
for name, o in objs.items():
    mn, mx = o["min"], o["max"]
    if name == "floor":
        if abs(mn[2] + 100) > 2 or abs(mx[2]) > 2: bad.append((name, "z", mn[2], mx[2]))
        px = [p for p in M["polygon"]]
        bx = [min(p[0] for p in px), min(p[1] for p in px), max(p[0] for p in px), max(p[1] for p in px)]
        if any(abs(v - w) > 2 for v, w in zip([mn[0], mn[1], mx[0], mx[1]], bx)): bad.append((name, "bbox", mn, mx))
    elif name == "ceiling":
        if abs(mn[2] - CEIL) > 2: bad.append((name, mn[2]))
    elif name.startswith("glass"):
        if not (900 < mn[2] < 1100 and 2300 < mx[2] < 2500): bad.append((name, mn[2], mx[2]))
    elif name.startswith("wall"):
        if mn[2] < -2 or mx[2] > CEIL + 2: bad.append((name, mn[2], mx[2]))
check("A1-2 bboxes", not bad, f"violations={bad or 'none'}")

# A1-3: classify edges
n = len(M["polygon"])
door_edges, win_edges = set(), set()
for i, o in enumerate(M["openings"]):
    # find edge index by matching model edge endpoints
    for j in range(n):
        a, b = M["polygon"][j], M["polygon"][(j + 1) % n]
        if ([round(v, 1) for v in a] == [round(v, 1) for v in o["edge"][0]]
                and [round(v, 1) for v in b] == [round(v, 1) for v in o["edge"][1]]):
            (door_edges if o["kind"] == "door" else win_edges).add(j)
bad = []
for j in range(n):
    p = I["probes"].get(f"edge{j:02d}")
    mid_in_span = True
    if j in door_edges:
        a, b = M["polygon"][j], M["polygon"][(j + 1) % n]
        midx = (a[0] + b[0]) / 2
        o = [o for o in M["openings"] if o["kind"] == "door"][0]
        mid_in_span = o["span"][0] <= midx <= o["span"][1]
        if mid_in_span and p["hit"]: bad.append((j, "door-mid should pass through", p))
        continue
    if j in win_edges:
        if not (p["hit"] and p["obj"].startswith("glass") and 250 <= p["dist"] <= 450):
            bad.append((j, "window edge", p))
    else:
        a, b = M["polygon"][j], M["polygon"][(j + 1) % n]
        import math as _m
        elen = _m.dist(a, b)
        if elen >= 400:   # long edge: must hit ITS wall at ~300
            if not (p["hit"] and 280 <= p["dist"] <= 330 and p["obj"].startswith("wall")):
                bad.append((j, "solid edge", p))
        else:             # short jog: probe cone may clip a neighbour first — any wall within 330 proves closure
            if not (p["hit"] and p["dist"] <= 330 and p["obj"].startswith("wall")):
                bad.append((j, "short jog", p))
check("A1-3 probes", not bad, f"violations={bad or 'none'} (door edge passes, windows hit glass)")

enc = I["enclosure"]
check("A1-4 enclosure", enc and enc["rays"] > 200 and not enc["unexplained_escapes"],
      f"rays={enc['rays']} unexplained={len(enc['unexplained_escapes'])}")

rd = OUT / "renders" / "stage1"
files = [rd / f"{c['id']}-{p}.png" for c in M["cameras"] for p in ("vis", "id")]
missing = [f.name for f in files if not f.exists()]
detail = f"missing={missing}"
ok = not missing
if ok:
    dark = []
    for f in files:
        if f.name.endswith("vis.png"):
            a = np.asarray(Image.open(f).convert("L"))
            if a.mean() < 15: dark.append(f.name)
    idtop = np.asarray(Image.open(rd / "cam-top-id.png").convert("RGB")).reshape(-1, 3)
    def srgb(v):
        return v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
    def has(rgb, arr, tol=25):
        t = np.array([round(srgb(v) * 255) for v in rgb])
        return (np.abs(arr.astype(int) - t).max(axis=1) < tol).sum()
    floor_px = has((0.1, 0.1, 0.8), idtop)
    identry = np.asarray(Image.open(rd / "cam-entry-id.png").convert("RGB")).reshape(-1, 3)
    glass_px = has((0.1, 0.8, 0.8), identry)
    wall_px = has((0.8, 0.1, 0.1), identry)
    ok = not dark and floor_px > 50000 and glass_px > 500 and wall_px > 50000
    detail = f"dark={dark or 'none'} id-top floor_px={floor_px} entry glass_px={glass_px} wall_px={wall_px}"
check("A1-5 renders", ok, detail)

passed = all(r["pass"] for r in R)
json.dump({"gate": "A1", "pass": passed, "checks": R}, open(OUT / "audits" / "a1_report.json", "w"), indent=1)
for r in R: print(("PASS " if r["pass"] else "FAIL "), r["rule"], "—", r["detail"])
print("=> A1", "ALL PASS" if passed else "FAILED")
sys.exit(0 if passed else 1)
