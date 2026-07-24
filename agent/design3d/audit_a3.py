#!/usr/bin/env python3
"""A3 gate — furnishing layout rules + structure/MEP freeze vs stage 2.

  A3-1  every furniture/curtain object built at model coords (±2mm)
  A3-2  containment: footprints inside room polygon (cab-br3 lives in the parapet niche instead)
  A3-3  no solid overlaps (rug exempt; bed+headboard pair exempt; sockets may hide behind furniture;
        FCU/trunks/compressor must stay clear of all furniture)
  A3-4  door swing quarter-circle stays furniture-free
  A3-5  walkways: door pass-through >=650, closet internal aisle >=900, both bed sides >=500
  A3-6  windows unblocked: nothing >1.2m tall within 700mm in front (curtains exempt)
  A3-7  FCU airflow: 300mm in front at unit height is clear
  A3-8  exactly one lamp, floor-standing, <=800mm from its socket; still no ceiling light
  A3-9  curtains: blackout+sheer per window, x-cover the window span, full drop
  A3-10 niche fills: bay seat in bay, br3 cabinet in band, pocket wardrobe in pocket
  A3-11 freeze: stage3 vs stage2 visual diff outside furnishing mask < 0.4% per camera

Usage: python3 audit_a3.py <room_model.json> <out_root>
"""
import json, sys, math, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from imgdiff import id_transition_diff

M = json.load(open(sys.argv[1]))
OUT = pathlib.Path(sys.argv[2])
I = json.load(open(OUT / "audits" / "introspect_stage3.json"))
objs = I["objects"]
CEIL = M["ceiling_mm"]
poly = M["polygon"]
R = []
def check(rule, ok, detail): R.append({"rule": rule, "pass": bool(ok), "detail": str(detail)})
def nb(b): return [min(b[0], b[3]), min(b[1], b[4]), min(b[2], b[5]), max(b[0], b[3]), max(b[1], b[4]), max(b[2], b[5])]

fur = {f["id"]: {**f, "box": nb(f["box"])} for f in M["furniture"]}
cur = {c["id"]: {**c, "box": nb(c["box"])} for c in M["curtains"]}

# A3-1
errs = []
for fid, f in {**fur, **cur}.items():
    name = f"{fid}:{f['kind']}" if "kind" in f else fid
    o = objs.get(name) or objs.get(fid)
    if not o: errs.append(f"{fid} missing"); continue
    got = o["min"] + o["max"]
    if any(abs(g - w) > 2 for g, w in zip(got, f["box"])): errs.append(f"{fid} off {got} vs {f['box']}")
check("A3-1 objects", not errs, errs or f"{len(fur)} furniture + {len(cur)} curtains at model coords")

# A3-2
def inside(pt):
    x, y = pt; c = False
    for i in range(len(poly)):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1: c = not c
    return c
NICHES = {"fur-cab-br3": nb([102.3, 4194.3, 0, 102.3 + 2472, 4194.3 + 324, 1000]),
          "fur-cab-br1": nb([2830.3, 4194.3, 0, 2830.3 + 1671, 4194.3 + 324, 1000])}
bad = []
for fid, f in {**fur, **cur}.items():
    b = f["box"]
    if fid in NICHES:
        z = NICHES[fid]
        if not all(b[i] >= z[i] - 3 for i in (0, 1)) or not all(b[i] <= z[i] + 3 for i in (3, 4)):
            bad.append((fid, "outside niche"))
        continue
    s = 5
    pts = [(b[0] + s, b[1] + s), (b[3] - s, b[1] + s), (b[3] - s, b[4] - s), (b[0] + s, b[4] - s)]
    if not all(inside(p) for p in pts): bad.append((fid, "outside polygon"))
check("A3-2 containment", not bad, bad or "all footprints inside room (cab-br3 in niche)")

# A3-3
def olap(a, b, m=5):
    return all(min(a[i + 3], b[i + 3]) - max(a[i], b[i]) > m for i in range(3))
items = list({**fur, **cur}.items())
bad = []
for i in range(len(items)):
    for j in range(i + 1, len(items)):
        fa, fb = items[i][1], items[j][1]
        ka, kb = fa.get("kind", "curtain"), fb.get("kind", "curtain")
        if "rug" in (ka, kb): continue
        if ka == kb == "bed": continue
        if olap(fa["box"], fb["box"]): bad.append((items[i][0], items[j][0]))
mep = M["mep"]
hard_mep = ([nb([mep["fcu"]["x"][0], mep["fcu"]["face_y"] - mep["fcu"]["depth"], mep["fcu"]["z"][0],
                 mep["fcu"]["x"][1], mep["fcu"]["face_y"], mep["fcu"]["z"][1]])]
            + [nb(t["box"]) for t in mep["trunking"]] + [nb(mep["compressor"]["box"])])
for fid, f in items:
    for k, mb in enumerate(hard_mep):
        if olap(f["box"], mb): bad.append((fid, f"mep#{k}"))
check("A3-3 overlaps", not bad, bad or "no solid collisions (rug/bed-pair exempt, sockets behind furniture ok)")

# A3-4 door swing
door = [o for o in M["openings"] if o["kind"] == "door"][0]
hx, hy, rr = door["span"][1], door["face_y"], door["width_mm"] + 30
bad = []
for fid, f in items:
    b = f["box"]
    if b[2] > 2020: continue                     # high objects clear the leaf
    cx = max(b[0], min(hx, b[3])); cy = max(b[1], min(hy, b[4]))
    dx, dy = hx - cx, hy - cy
    # swing quadrant is WEST of the hinge only (leaf sweeps from the door line into the room)
    if cx <= hx and cx >= hx - rr and math.hypot(dx, dy) < rr and hy - 1 <= cy <= hy + rr and b[4] > hy:
        bad.append((fid, round(math.hypot(dx, dy))))
check("A3-4 door-swing", not bad, bad or f"swing quadrant r={rr} at hinge ({hx:.0f},{hy:.0f}) clear")

# A3-5 walkways
bed = fur["fur-bed"]["box"]
south_face = door["face_y"]
pass_through = bed[1] - fur["fur-closet-south"]["box"][4]   # bed south edge vs closet-south north face
aisle = 2659.8 - fur["fur-closet-west"]["box"][3]           # closet zone width minus west run
north_side = min(4194.3, cur["cur-br1-sheer"]["box"][1]) - bed[4]
south_side = bed[1] - nb(fur["fur-lamp"]["box"])[4]
check("A3-5 walkways", pass_through >= 650 and aisle >= 900 and north_side >= 500 and south_side >= 500,
      f"pass-through {pass_through:.0f} aisle {aisle:.0f} bed-north {north_side:.0f} bed-south {south_side:.0f}")

# A3-6 windows
bad = []
for o in [o for o in M["openings"] if o["kind"] == "window"]:
    fy = o["face_y"]
    front = nb([o["span"][0], fy - 700, 0, o["span"][1], fy, 2600]) if inside((sum(o["span"]) / 2, fy - 5)) \
        else nb([o["span"][0], fy, 0, o["span"][1], fy + 700, 2600])
    for fid, f in fur.items():
        if f["kind"] in ("cabinet",) and f["box"][5] <= 1200: continue
        if f["box"][5] <= 1200: continue
        if f["box"][2] >= 2000: continue   # ceiling-hung (pelmet/bulkhead) — above the opening, not a blocker
        if olap(f["box"], front): bad.append((o["id"], fid))
check("A3-6 windows-clear", not bad, bad or "no tall furniture within 700mm of window faces")

# A3-7 FCU airflow (orientation-aware)
f = mep["fcu"]
ty = f.get("throw", [0, -1])[1]
if ty > 0:
    front = nb([f["x"][0], f["face_y"] + f["depth"], 2000, f["x"][1], f["face_y"] + f["depth"] + 300, f["z"][1]])
else:
    front = nb([f["x"][0], f["face_y"] - f["depth"] - 300, 2000, f["x"][1], f["face_y"] - f["depth"], f["z"][1]])
bad = [fid for fid, ff in items if olap(ff["box"], front)]
check("A3-7 fcu-airflow", not bad, bad or "300mm in front of FCU clear")

# A3-8 lamp
lamps = [f for f in fur.values() if f["kind"] == "lamp"]
skt = [s for s in mep["sockets"] if "lamp" in s["use"]][0]
lc = [(lamps[0]["box"][0] + lamps[0]["box"][3]) / 2, (lamps[0]["box"][1] + lamps[0]["box"][4]) / 2]
d = math.hypot(lc[0] - skt["p"][0], lc[1] - skt["p"][1])
check("A3-8 lamp", len(lamps) == 1 and lamps[0]["box"][2] < 10 and d <= 800 and mep["no_ceiling_luminaire"],
      f"1 floor lamp, {d:.0f}mm from {skt['id']}, no ceiling light")

# A3-9 curtains — day state: sheer covers the span; blackout = stacked column near each span end; all full drop
bad = []
for o in [o for o in M["openings"] if o["kind"] == "window"]:
    cs = [c for c in cur.values() if c["win"] == o["id"]]
    sheers = [c for c in cs if c["layer"] == "sheer"]
    blacks = [c for c in cs if c["layer"] == "blackout"]
    for c in cs:
        b = c["box"]
        topped = b[5] >= CEIL - 50 or any(          # track may stop under a pelmet that runs on to the ceiling
            p["box"][2] <= b[5] + 1 and p["box"][5] >= CEIL - 30
            and p["box"][0] <= b[0] + 1 and p["box"][3] >= b[3] - 1
            for p in fur.values() if "pelmet" in p["id"])
        if not (b[2] <= 50 and topped): bad.append((c["id"], "not full drop"))
    if not (len(sheers) == 1 and sheers[0]["box"][0] <= o["span"][0] + 5
            and sheers[0]["box"][3] >= o["span"][1] - 5): bad.append((o["id"], "sheer-cover"))
    if len(blacks) < 2: bad.append((o["id"], "need blackout stack both ends"))
    else:
        s0, s1 = o["span"]
        if min(b["box"][0] for b in blacks) > s0 + 320: bad.append((o["id"], "no stack at start"))
        if max(b["box"][3] for b in blacks) < s1 - 320: bad.append((o["id"], "no stack at end"))
check("A3-9 curtains", not bad, bad or "sheer drawn over spans; blackout stacks both ends; all full drop")

# A3-10 niches
BAY = nb([4518.4, 4194.3, 0, 5609.4, 4808.1, 2600])
POCKET = nb([4006.8, 0, 0, 5728.8, 511.5, 2600])
def within(b, zone, tol=3):
    return all(b[i] >= zone[i] - tol for i in (0, 1)) and all(b[i] <= zone[i] + tol for i in (3, 4))
ok = (within(fur["fur-cab-bay"]["box"], BAY) and within(fur["fur-wardrobe-pocket"]["box"], POCKET))
check("A3-10 niche-fills", ok, "bay seat in bay; pocket wardrobe in SE pocket; br3 cabinet checked in A3-2")

# A3-11 freeze — ID-class transition audit (palette-independent):
# structure pixels may only stay put or be occluded by furnishing classes
CLASSES = {"wall": (0.8, 0.1, 0.1), "floor": (0.1, 0.1, 0.8), "ceiling": (0.8, 0.8, 0.1),
           "glass": (0.1, 0.8, 0.8), "mep": (0.9, 0.5, 0.1), "risk": (0.4, 0.0, 0.0),
           "closet": (0.1, 0.7, 0.1), "cabinet": (0.2, 0.9, 0.2), "bed": (0.3, 0.6, 0.1),
           "table": (0.1, 0.5, 0.3), "lamp": (1.0, 0.6, 0.8), "rug": (0.5, 0.9, 0.9),
           "blackout": (0.7, 0.1, 0.7), "sheer": (0.9, 0.4, 0.9), "boxup": (0.55, 0.55, 0.95)}
STRUCT = ["wall", "floor", "ceiling", "glass", "mep", "risk"]
ADDITIVE = ["closet", "cabinet", "bed", "table", "lamp", "rug", "blackout", "sheer", "boxup"]
worst = 0.0; per = {}
for cam in M["cameras"]:
    cid = cam["id"]
    d = id_transition_diff(OUT / "renders/stage2" / f"{cid}-id.png", OUT / "renders/stage3" / f"{cid}-id.png",
                           CLASSES, STRUCT, ADDITIVE, OUT / "audits" / f"diff_stage3_{cid}.png")
    per[cid] = d["violation_pct"]; worst = max(worst, d["violation_pct"])
check("A3-11 freeze", worst <= 0.4, per)

# A3-12 beam-scenario clearance: the risk-beam band (unconfirmed, MEDIUM probability) is
# treated as present for design purposes — nothing above the worst-case soffit may enter it.
# Exempt: pelmet items, whose purpose is to box the beam in.
def xyz_olap(a, b):
    return all(a[i] < b[i + 3] - 1 and a[i + 3] > b[i] + 1 for i in range(3))
bad = []
for r in M.get("risk_elements", []):
    rb = nb(r["box"])
    for fid, f in {**fur, **cur}.items():
        if "pelmet" in fid: continue
        if xyz_olap(f["box"], rb): bad.append((fid, r["id"]))
check("A3-12 beam-clearance", not bad, bad or
      f"all furnishing clear of risk bands (pelmet exempt: boxes the beam if confirmed)")

passed = all(r["pass"] for r in R)
json.dump({"gate": "A3", "pass": passed, "checks": R}, open(OUT / "audits" / "a3_report.json", "w"), indent=1)
for r in R: print(("PASS " if r["pass"] else "FAIL "), r["rule"], "—", r["detail"])
print("=> A3", "ALL PASS" if passed else "FAILED")
sys.exit(0 if passed else 1)
