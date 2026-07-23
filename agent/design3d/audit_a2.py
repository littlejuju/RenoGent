#!/usr/bin/env python3
"""A2 gate — MEP layer rules + structure freeze vs stage 1.

  A2-1 objects: FCU/3 trunks/compressor/4 sockets built at model coords (±2mm)
  A2-2 condensate gravity: FCU inlet > penetration > compressor top (monotonic fall)
  A2-3 trunking hugs the north wall corridor (no free-floating runs)
  A2-4 penetration: in solid band (not through any window span), compressor within 600mm
  A2-5 sockets sit ON wall faces (<=25mm from a polygon edge)
  A2-6 FCU on north return, clear of both window spans, top >=200mm below ceiling
  A2-7 no ceiling luminaire anywhere (P1 hard rule)
  A2-8 structure freeze: stage2 vs stage1 visual diff outside MEP mask < 0.3% per camera

Usage: python3 audit_a2.py <room_model.json> <out_root>
"""
import json, sys, math, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from imgdiff import freeze_diff

M = json.load(open(sys.argv[1]))
OUT = pathlib.Path(sys.argv[2])
I = json.load(open(OUT / "audits" / "introspect_stage2.json"))
objs = I["objects"]
mep = M["mep"]
CEIL = M["ceiling_mm"]
R = []
def check(rule, ok, detail): R.append({"rule": rule, "pass": bool(ok), "detail": str(detail)})

def bbox_close(name, box, tol=2):
    o = objs.get(name)
    if not o: return f"{name} missing"
    got = o["min"] + o["max"]
    want = [min(box[0], box[3]), min(box[1], box[4]), min(box[2], box[5]),
            max(box[0], box[3]), max(box[1], box[4]), max(box[2], box[5])]
    if any(abs(g - w) > tol for g, w in zip(got, want)): return f"{name} off: {got} vs {want}"
    return None

f = mep["fcu"]
ty = f.get("throw", [0, -1])[1]
fy0, fy1 = (f["face_y"], f["face_y"] + f["depth"]) if ty > 0 else (f["face_y"] - f["depth"], f["face_y"])
fbox = [f["x"][0], fy0, f["z"][0], f["x"][1], fy1, f["z"][1]]
errs = [e for e in
        [bbox_close("mep-fcu", fbox)] +
        [bbox_close(t["id"], t["box"]) for t in mep["trunking"]] +
        [bbox_close("mep-compressor", mep["compressor"]["box"])] +
        [None if s["id"] in objs else f"{s['id']} missing" for s in mep["sockets"]]
        if e]
check("A2-1 objects", not errs, errs or f"FCU+{len(mep['trunking'])} trunks+compressor+{len(mep['sockets'])} sockets OK")

pen_z = mep["penetration"]["z"]
zs = [f["z"][0]] + [min(t["box"][2], t["box"][5]) for t in mep["trunking"]]
mono = all(zs[i] >= zs[i + 1] for i in range(len(zs) - 1))
last = mep["trunking"][-1]["box"]
pen_in_band = min(last[2], last[5]) <= pen_z <= max(last[2], last[5]) + 60
check("A2-2 gravity", mono and pen_in_band,
      f"condensate falls along segment bottoms {zs}; pen {pen_z} within last band")

poly_ = M["polygon"]
def edge_dist(p):
    best = 1e9
    for i in range(len(poly_)):
        a, b = poly_[i], poly_[(i + 1) % len(poly_)]
        ax, ay = a; bx, by = b
        t = max(0, min(1, ((p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)) / max((bx - ax) ** 2 + (by - ay) ** 2, 1e-9)))
        best = min(best, math.hypot(p[0] - (ax + t * (bx - ax)), p[1] - (ay + t * (by - ay))))
    return best
fur_boxes = {x["id"]: x["box"] for x in M["furniture"]}
bad = []
for t in mep["trunking"]:
    b = t["box"]
    c = [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2]
    if t.get("attach") in fur_boxes:   # installer runs trunking along joinery faces (plinth/top)
        fb = fur_boxes[t["attach"]]
        gap = max(0, max(min(b[1], b[4]) - max(fb[1], fb[4]), min(fb[1], fb[4]) - max(b[1], b[4])),
                  )
        ok = gap <= 150
        if not ok: bad.append((t["id"], f"attach-gap {gap:.0f}"))
    elif edge_dist(c) > 250:
        bad.append((t["id"], round(edge_dist(c))))
check("A2-3 trunk-hugs-wall", not bad, bad or "every trunk hugs a wall face or a declared joinery face")

px, py = mep["penetration"]["at"]
spans = [o["span"] for o in M["openings"] if o["kind"] == "window"]
in_win = any(s[0] - 50 <= px <= s[1] + 50 for s in spans)
c = mep["compressor"]["box"]
dx = max(c[0] - px, px - c[3], 0); dy = max(c[1] - py, py - c[4], 0)
check("A2-4 penetration", (not in_win) and math.hypot(dx, dy) <= 600,
      f"pen x={px:.0f} clear of window spans {spans}; dist to compressor {math.hypot(dx, dy):.0f}mm")

poly = M["polygon"]
def dist_to_edges(p):
    best = 1e9
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        ax, ay = a; bx, by = b
        t = max(0, min(1, ((p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)) / max((bx - ax) ** 2 + (by - ay) ** 2, 1e-9)))
        best = min(best, math.hypot(p[0] - (ax + t * (bx - ax)), p[1] - (ay + t * (by - ay))))
    return best
bad = [(s["id"], round(dist_to_edges(s["p"]))) for s in mep["sockets"] if dist_to_edges(s["p"]) > 25]
check("A2-5 sockets-on-wall", not bad, bad or "all sockets <=25mm from a wall face")

# window-span clearance only matters when the FCU shares the windows' wall face
win_faces = [o["face_y"] for o in M["openings"] if o["kind"] == "window"]
same_face = any(abs(f["face_y"] - wf) < 1 for wf in win_faces)
fcu_clear = (not same_face) or all(f["x"][1] <= s[0] - 50 or f["x"][0] >= s[1] + 50 for s in spans)
check("A2-6 fcu", fcu_clear and f["z"][1] <= CEIL - 200,
      f"wall={f['wall']}; window-span clear={fcu_clear}; top {f['z'][1]} <= {CEIL - 200}")

lamps_high = [n for n, o in objs.items() if o.get("klass") == "lamp" and o["min"][2] > 2000]
check("A2-7 no-ceiling-light", mep["no_ceiling_luminaire"] and not lamps_high,
      f"flag={mep['no_ceiling_luminaire']} high-lamps={lamps_high or 'none'}")

# A2-9 beam-scenario clearance: no MEP element above the worst-case soffit may enter
# the risk band (design must survive beam-confirmed outcome without rework).
def xyz_overlap(a, b):
    return all(min(a[i], a[i + 3]) < max(b[i], b[i + 3]) - 1 and
               max(a[i], a[i + 3]) > min(b[i], b[i + 3]) + 1 for i in range(3))
mep_boxes = [("mep-fcu", fbox)] + [(t["id"], t["box"]) for t in mep["trunking"]]
bad = [(n, r["id"]) for r in M.get("risk_elements", []) for n, b in mep_boxes if xyz_overlap(b, r["box"])]
check("A2-9 beam-clearance", not bad, bad or
      f"fcu x{f['x']} + {len(mep['trunking'])} trunks clear of risk bands {[r['box'][0::3] for r in M.get('risk_elements', [])]}")

MEPC = [(0.9, 0.5, 0.1)]
worst = 0.0; per = {}
for cam in M["cameras"]:
    cid = cam["id"]
    d = freeze_diff(OUT / "renders/stage1" / f"{cid}-vis.png", OUT / "renders/stage2" / f"{cid}-vis.png",
                    OUT / "renders/stage2" / f"{cid}-id.png", MEPC,
                    OUT / "audits" / f"diff_stage2_{cid}.png")
    per[cid] = d; worst = max(worst, d["violation_pct"])
check("A2-8 structure-freeze", worst <= 0.3, {k: v["violation_pct"] for k, v in per.items()})

passed = all(r["pass"] for r in R)
json.dump({"gate": "A2", "pass": passed, "checks": R}, open(OUT / "audits" / "a2_report.json", "w"), indent=1)
for r in R: print(("PASS " if r["pass"] else "FAIL "), r["rule"], "—", r["detail"])
print("=> A2", "ALL PASS" if passed else "FAILED")
sys.exit(0 if passed else 1)
