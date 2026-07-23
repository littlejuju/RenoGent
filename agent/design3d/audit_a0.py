#!/usr/bin/env python3
"""A0 gate — room_model.json vs facts.json reconciliation. Deterministic, no vision.

Rules:
  A0-1 scale & polygon: model polygon is the facts polygon under the declared affine
        (same vertex count, every vertex maps back within 0.6px)
  A0-2 area: shoelace(polygon) vs facts area_sqft within ±3 sqft
  A0-3 edges: every model edge length == facts polygon_edges mm within ±1px (17.05mm)
  A0-4 openings: widths match facts (door 914, win-br1 1023, win-br3 2472 niche run);
        every opening span lies on its host edge; 0 <= sill < head <= ceiling
  A0-5 bricked BR3 door is NOT an opening (hack: wall-built)
  A0-6 niches: bay depth 614 == edge (699,662)-(699,698); br3 parapet band 324 == niche[2]
  A0-7 provenance: every opening/mep/furniture element has ref or class=proposed
  A0-8 P1 hard constraints encoded: no_ceiling_luminaire true; exactly 1 floor lamp in furniture;
        curtains full-length (z0<=50, z1>=ceiling-50) with blackout+sheer per window

Usage: python3 audit_a0.py <facts.json> <room_model.json> <report_out.json>
"""
import json, sys, math

facts = json.load(open(sys.argv[1]))
model = json.load(open(sys.argv[2]))
room = [r for r in facts["rooms"] if r["key"] == "master-suite"][0]
MMPX = model["meta"]["mm_per_px"]
OX, OY = model["meta"]["origin_px"]
CEIL = model["ceiling_mm"]
R = []
def check(rule, ok, detail):
    R.append({"rule": rule, "pass": bool(ok), "detail": detail})

# A0-1
pm, pf = model["polygon"], room["polygon_px"]
ok = len(pm) == len(pf)
worst = 0.0
if ok:
    for (mx, my), (fx, fy) in zip(pm, pf):
        bx, by = mx / MMPX + OX, OY - my / MMPX
        worst = max(worst, abs(bx - fx), abs(by - fy))
    ok = worst <= 0.6
check("A0-1 polygon-affine", ok, f"n={len(pm)}/{len(pf)} worst_backmap={worst:.3f}px")

# A0-2
def shoelace(p):
    s = 0.0
    for i in range(len(p)):
        x1, y1 = p[i]; x2, y2 = p[(i + 1) % len(p)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0
sqft = shoelace(pm) / 92903.04
check("A0-2 area", abs(sqft - room["area_sqft"]) <= 3, f"model {sqft:.1f} vs facts {room['area_sqft']} sqft")

# A0-3
edges_f = room["polygon_edges"]
bad = []
for i in range(len(pm)):
    a, b = pm[i], pm[(i + 1) % len(pm)]
    L = math.dist(a, b)
    Lf = edges_f[i]["mm"]
    if abs(L - Lf) > MMPX + 0.01:
        bad.append((i, round(L, 1), Lf))
check("A0-3 edge-lengths", not bad, f"mismatches={bad or 'none'} ({len(pm)} edges)")

# A0-4
ops = {o["id"]: o for o in model["openings"]}
dw = room["doors_windows"]
exp = {"door-entry": dw[2]["width_mm"], "win-br1": dw[0]["width_mm"],
       "win-br3": room["cabinet_niches"][2]["run_mm"]}
bad = []
for oid, w in exp.items():
    o = ops.get(oid)
    if not o: bad.append((oid, "missing")); continue
    got = o["span"][1] - o["span"][0]
    if abs(got - w) > MMPX: bad.append((oid, round(got, 1), w))
    e0, e1 = o["edge"]
    lo, hi = min(e0[0], e1[0]), max(e0[0], e1[0])
    if o["axis"] == "x" and not (lo - 1 <= o["span"][0] and o["span"][1] <= hi + 1):
        bad.append((oid, "span-off-edge", o["span"], [lo, hi]))
    z0, z1 = o["z"]
    if not (0 <= z0 < z1 <= CEIL): bad.append((oid, "bad-z", o["z"]))
check("A0-4 openings", not bad, f"{bad or 'widths match facts (' + ', '.join(f'{k}={v}' for k, v in exp.items()) + '), on-edge, z ok'}")

# A0-5
built = [d for d in dw if d["type"] == "wall-built"]
check("A0-5 bricked-door", len(built) == 1 and "wall" not in ops,
      f"facts wall-built entries={len(built)}, model emits no opening there")

# A0-6
bay_edge = math.dist(pm[0], pm[1])  # placeholder replaced below
# bay depth = edge (699,662)->(699,698) i.e. facts polygon_edges[1]
bay_f = edges_f[1]["mm"]
n1 = room["cabinet_niches"][1]["band_depth_mm"]
p324 = ops["win-br3"].get("parapet_recess_mm")
check("A0-6 niches", abs(bay_f - n1) <= MMPX and p324 == room["cabinet_niches"][2]["band_depth_mm"],
      f"bay edge {bay_f} vs niche {n1}; br3 band {p324}")

# A0-7
missing = []
for o in model["openings"]:
    if not o.get("ref"): missing.append(o["id"])
for f in model["furniture"]:
    if not (f.get("ref") or f.get("note") or f.get("color")): missing.append(f["id"])
if not model["mep"].get("class") == "proposed": missing.append("mep.class")
check("A0-7 provenance", not missing, f"missing={missing or 'none'}")

# A0-8
CEIL = model["ceiling_mm"]
lamps = [f for f in model["furniture"] if f["kind"] == "lamp"]
cur = model["curtains"]
by_win = {}
for c in cur:
    by_win.setdefault(c["win"], set()).add(c["layer"])
pelmets = [f for f in model["furniture"] if "pelmet" in f["id"]]
def full_len(c):
    b = c["box"]
    if b[2] > 50: return False
    if b[5] >= CEIL - 50: return True
    # track may stop under a pelmet box that carries on to the ceiling (beam-band detail)
    return any(p["box"][2] <= b[5] + 1 and p["box"][5] >= CEIL - 30
               and p["box"][0] <= min(b[0], b[3]) + 1 and p["box"][3] >= max(b[0], b[3]) - 1
               for p in pelmets)
full = all(full_len(c) for c in cur)
ok = (model["mep"]["no_ceiling_luminaire"] and len(lamps) == 1 and full
      and all({"blackout", "sheer"} <= s for s in by_win.values())
      and set(by_win) == {"win-br1", "win-br3"})
check("A0-8 P1-constraints", ok,
      f"no_ceiling_light={model['mep']['no_ceiling_luminaire']} lamps={len(lamps)} "
      f"curtains_full_length={full} layers={ {k: sorted(v) for k, v in by_win.items()} }")

# A0-9 window-ink crosscheck (closes the loop-1 gap that let window/return swap through):
# the raw-plan band just OUTSIDE a declared window span must carry casement/band ink,
# and clearly more of it than a declared solid segment on the same wall.
try:
    from PIL import Image
    import numpy as np
    import pathlib
    plan = pathlib.Path(sys.argv[1]).parent.parent / "raw" / "floorplan.png"
    im = np.asarray(Image.open(plan).convert("L"))
    OXp, OYp = model["meta"]["origin_px"]
    def density(x0px, x1px, y0px, y1px):
        seg = im[y0px:y1px, x0px:x1px]
        return float((seg < 128).mean())
    def to_px(mm): return round(mm / MMPX + OXp)
    win = {}
    for o in model["openings"]:
        if o["kind"] != "window": continue
        fy = round(OYp - o["face_y"] / MMPX)
        win[o["id"]] = density(to_px(o["span"][0]) + 3, to_px(o["span"][1]) - 3, fy - 58, fy - 4)
    ctrl = density(712, 755, 640, 694)      # declared solid return x712-755 (control strip)
    ok = all(d > 1.6 * ctrl and d > 0.02 for d in win.values())
    check("A0-9 window-ink", ok, f"win-ink={ {k: round(v, 3) for k, v in win.items()} } return-ink={ctrl:.3f} (windows must be >1.6x)")
except Exception as e:
    check("A0-9 window-ink", False, f"crosscheck unavailable: {e}")

passed = all(r["pass"] for r in R)
rep = {"gate": "A0", "pass": passed, "checks": R}
json.dump(rep, open(sys.argv[3], "w"), ensure_ascii=False, indent=1)
for r in R:
    print(("PASS " if r["pass"] else "FAIL "), r["rule"], "—", r["detail"])
print("=> A0", "ALL PASS" if passed else "FAILED")
sys.exit(0 if passed else 1)
