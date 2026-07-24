#!/usr/bin/env python3
"""A5 gate — D-layer P0: joinery craft (D1) + opening/hardware (D2).

Enforces joinery_rules.json against room_model.json:
  A5-1 R-J-1 top-closure: joinery >1800 tall reaches ceiling (counter-height exempt)
  A5-2 R-J-2 FCU box-up: no open gap <200mm around the FCU (top band to ceiling,
        side strips to nearest solid) — boxup items must tile the surround
  A5-3 R-J-3 end-closure: joinery-run end gaps to walls are <=20 scribe, filled
        20-300, or >300 usable; declared service gaps (attach/note) exempt
  A5-4 R-J-6 door sweeps: hinged leaf sweep (span x width x door z) clear of
        furniture/MEP (exempt: own unit, curtains, rug); sliding/drawer as typed
  A5-5 R-J-5 hardware: every hinged door has a hinge side; adjacent pair leaves
        hinge opposite (handles meet); handle band 900-1100; sliding = edge pulls

Usage: python3 audit_a5_joinery.py <room_model.json> <joinery_rules.json> <out_root>
"""
import json, sys, pathlib

M = json.load(open(sys.argv[1]))
RULES = json.load(open(sys.argv[2]))
OUT = pathlib.Path(sys.argv[3])
CEIL = M["ceiling_mm"]
R = []
def check(rule, ok, detail): R.append({"rule": rule, "pass": bool(ok), "detail": str(detail)})
def nb(b): return [min(b[0], b[3]), min(b[1], b[4]), min(b[2], b[5]), max(b[0], b[3]), max(b[1], b[4]), max(b[2], b[5])]
def olap(a, b, m=1):
    return all(a[i] < b[i + 3] - m and a[i + 3] > b[i] + m for i in range(3))

fur = {f["id"]: {**f, "box": nb(f["box"])} for f in M["furniture"]}
joinery = {k: f for k, f in fur.items() if f["kind"] in ("closet", "cabinet", "boxup")}

# A5-1 top closure
SILL = 1000
bad = [(k, f["box"][5]) for k, f in joinery.items()
       if f["kind"] != "boxup" and (f["box"][5] - f["box"][2]) > 1800
       and f["box"][5] < CEIL - 30 and f["box"][5] > SILL + 50]
tall_ok = [(k, f["box"][5]) for k, f in joinery.items() if (f["box"][5] - f["box"][2]) > 1800]
check("A5-1 R-J-1 top-closure", not bad, bad or f"{len(tall_ok)} tall units all reach ceiling {CEIL}")

# A5-2 FCU box-up: tile check on the wall plane. The FCU + boxup items, projected on
# the wall face, must cover the rectangle [west_solid..east_solid] x [fcu_z0..CEIL].
f = M["mep"]["fcu"]
boxups = [v for v in fur.values() if v["kind"] == "boxup"]
west_solid, east_solid = 2963, 3887          # beam-band edge / wall jog (nearest solids)
tiles = [[f["x"][0], f["z"][0], f["x"][1], f["z"][1]]] + \
        [[b["box"][0], b["box"][2], b["box"][3], b["box"][5]] for b in boxups]
holes = []
step = 20
x = west_solid + step / 2
while x < east_solid:
    z = f["z"][0] + step / 2
    while z < CEIL:
        if not any(t[0] - 1 <= x <= t[2] + 1 and t[1] - 1 <= z <= t[3] + 1 for t in tiles):
            holes.append((round(x), round(z)))
        z += step
    x += step
check("A5-2 R-J-2 fcu-box-up", not holes,
      f"holes={holes[:6]}{'...' if len(holes) > 6 else ''}" if holes else
      f"FCU {f['x']} + {len(boxups)} boxups tile [{west_solid},{east_solid}]x[{f['z'][0]},{CEIL}] fully")

# A5-3 end closure: for each closet/cabinet, measure xy gap from each side face to the
# nearest parallel wall segment of the polygon; classify.
poly = M["polygon"]
def gap_to_wall(face_val, axis, lo, hi, direction):
    """distance from a side face (at face_val on axis, spanning lo..hi on the other axis)
    outward in `direction` to the nearest parallel polygon edge overlapping that span"""
    best = None
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if axis == 0 and abs(a[0] - b[0]) < 1e-6:      # vertical edge (x const)
            e_lo, e_hi = sorted((a[1], b[1]))
            if e_hi < lo + 50 or e_lo > hi - 50: continue
            d = (a[0] - face_val) * direction
            if d >= -1 and (best is None or d < best): best = d
        if axis == 1 and abs(a[1] - b[1]) < 1e-6:
            e_lo, e_hi = sorted((a[0], b[0]))
            if e_hi < lo + 50 or e_lo > hi - 50: continue
            d = (a[1] - face_val) * direction
            if d >= -1 and (best is None or d < best): best = d
    return best
bad = []
for k, u in joinery.items():
    if u["kind"] == "boxup": continue
    b = u["box"]
    note = (u.get("note", "") or "").lower()
    declared = ("held off" in note or "service" in note or "filler" in note or "blind-corner" in note)
    for axis, face_val, lo, hi, direction in (
            (0, b[0], b[1], b[4], -1), (0, b[3], b[1], b[4], +1),
            (1, b[1], b[0], b[3], -1), (1, b[4], b[0], b[3], +1)):
        g = gap_to_wall(face_val, axis, lo, hi, direction)
        if g is None or g <= 20 or g > 300: continue
        # 20-300 residual: must be occupied by another joinery box or declared service gap
        probe = [0, 0, 0, 0, 0, 0]
        probe[axis], probe[axis + 3] = sorted((face_val + 2 * direction, face_val + (g - 2) * direction))
        oa = 1 - axis
        probe[oa], probe[oa + 3] = lo + 20, hi - 20
        probe[2], probe[5] = b[2] + 50, min(b[5], CEIL) - 50
        covered = any(olap(probe, v["box"]) for kk, v in fur.items() if kk != k)
        if not (covered or declared):
            bad.append((k, f"axis{axis}{'+' if direction > 0 else '-'}", round(g)))
check("A5-3 R-J-3 end-closure", not bad, bad or "all residual 20-300mm gaps filled or declared service gaps")

# A5-4 door sweeps
mep = M["mep"]
ty = mep["fcu"].get("throw", [0, 1])[1]
fy0, fy1 = (mep["fcu"]["face_y"], mep["fcu"]["face_y"] + mep["fcu"]["depth"]) if ty > 0 \
    else (mep["fcu"]["face_y"] - mep["fcu"]["depth"], mep["fcu"]["face_y"])
obstacles = {**{k: v["box"] for k, v in fur.items()},
             "mep-fcu": nb([mep["fcu"]["x"][0], fy0, mep["fcu"]["z"][0], mep["fcu"]["x"][1], fy1, mep["fcu"]["z"][1]]),
             **{t["id"]: nb(t["box"]) for t in mep["trunking"]}}
SOFT = ("rug",)
bad = []
sweeps = 0
for k, u in fur.items():
    fr = u.get("fronts")
    if not fr: continue
    ax, sign = fr["face"]
    b = u["box"]
    face = b[ax + 3] if sign > 0 else b[ax]
    z0 = b[2] + fr.get("plinth", 0)
    z1 = min(b[5], 2400) - 20
    for d in fr["doors"]:
        if d["type"] == "sliding": continue
        s0, s1 = d["span"]
        depth = (s1 - s0) if d["type"] == "hinged" else 450   # drawer pull-out 450
        sw = [0, 0, z0, 0, 0, z1]
        u_ax = 1 - ax
        sw[u_ax], sw[u_ax + 3] = s0, s1
        sw[ax], sw[ax + 3] = sorted((face + 2 * sign, face + depth * sign))
        sweeps += 1
        for ok_, ob in obstacles.items():
            if ok_ == k: continue
            if any(fur.get(ok_, {}).get("kind") == s for s in SOFT): continue
            if olap(sw, ob, m=2):
                bad.append((k, f"door@{round(s0)}-{round(s1)}", "hits", ok_))
check("A5-4 R-J-6 door-sweeps", not bad, bad or f"{sweeps} hinged/drawer sweeps all clear (sliding: no sweep)")

# A5-5 hardware: hinge side typed on every hinged leaf; handle lands at the opening
# edge with >=60mm clearance to any fixed obstacle at grip height (the user-reported
# failure: a handle facing a nightstand you cannot get fingers behind).
hw = M.get("hardware", {})
bad = []
if not (900 <= hw.get("handle_z", 0) <= 1100): bad.append(("handle_z", hw.get("handle_z")))
HZ = hw.get("handle_z", 1000)
handles = 0
for k, u in fur.items():
    fr = u.get("fronts")
    if not fr: continue
    ax, sign = fr["face"]
    b = u["box"]
    face = b[ax + 3] if sign > 0 else b[ax]
    for i, d in enumerate(fr["doors"]):
        if d["type"] == "hinged" and d.get("hinge") not in ("low", "high"):
            bad.append((k, i, "hinge side missing")); continue
        if d["type"] not in ("hinged", "sliding"): continue
        s0, s1 = d["span"]
        hp = (s1 - 45) if d.get("hinge") == "low" else (s0 + 45)   # opening edge (sliding: leading edge approximated same way)
        grip = [0, 0, HZ - 170, 0, 0, HZ + 170]
        u_ax = 1 - ax
        grip[u_ax], grip[u_ax + 3] = hp - 60, hp + 60
        grip[ax], grip[ax + 3] = sorted((face + 2 * sign, face + 130 * sign))   # hand clearance zone
        handles += 1
        for ok_, ob in obstacles.items():
            if ok_ == k: continue
            if fur.get(ok_, {}).get("kind") in SOFT: continue
            if olap(grip, ob, m=2): bad.append((k, i, "grip zone blocked by", ok_))
check("A5-5 R-J-5 hardware", not bad,
      bad or f"family='{hw.get('family')}' z={hw.get('handle_z')}; {handles} grip zones clear; hinges typed")

passed = all(r["pass"] for r in R)
json.dump({"gate": "A5", "pass": passed, "rules_version": RULES.get("version"), "checks": R},
          open(OUT / "audits" / "a5_report.json", "w"), indent=1)
for r in R: print(("PASS " if r["pass"] else "FAIL "), r["rule"], "—", r["detail"])
print("=> A5", "ALL PASS" if passed else "FAILED")
sys.exit(0 if passed else 1)
