#!/usr/bin/env python3
"""A4 gate — occupant-experience (ID/UX) rules, driven by ux_rules.json.

  A4-1 (R-UX-1) FCU direct-throw footprint clear of the pillow zone
  A4-2 (R-UX-2) FCU not above the headboard wall span
  A4-3 rules provenance present (every gating rule must say who taught it / industry source)

Usage: python3 audit_a4_ux.py <room_model.json> <out_root>
"""
import json, sys, pathlib

M = json.load(open(sys.argv[1]))
OUT = pathlib.Path(sys.argv[2])
RULES = json.load(open(pathlib.Path(__file__).parent / "ux_rules.json"))["rules"]
R = []
def check(rule, ok, detail): R.append({"rule": rule, "pass": bool(ok), "detail": str(detail)})

fcu = M["mep"]["fcu"]
throw = fcu.get("throw", [0, -1])
bed = [f for f in M["furniture"] if f["id"] == "fur-bed"][0]["box"]
bx = [min(bed[0], bed[3]), min(bed[1], bed[4]), max(bed[0], bed[3]), max(bed[1], bed[4])]

# pillow zone: 480mm strip at the head end = the bed side touching a wall (largest x here: east wall)
head_x = bx[2]
pillow = [head_x - 480, bx[1], head_x, bx[3]]

fx0, fx1 = fcu["x"]
fy = fcu["face_y"]
T = 2600
if throw[1] < 0:
    rect = [fx0 - 200, fy - fcu["depth"] - T, fx1 + 200, fy]
elif throw[1] > 0:
    rect = [fx0 - 200, fy, fx1 + 200, fy + fcu["depth"] + T]
else:
    rect = [fx0, fy, fx1, fy]  # x-throw not used yet
ovl = not (rect[2] <= pillow[0] or rect[0] >= pillow[2] or rect[3] <= pillow[1] or rect[1] >= pillow[3])
check("A4-1 R-UX-1 throw-vs-pillow", not ovl,
      f"throw rect {[round(v) for v in rect]} vs pillow zone {[round(v) for v in pillow]} -> {'OVERLAP' if ovl else 'clear'}")

# A4-2: same wall as bed head? bed head touches east wall (x = head_x near wall plane)
same_wall = abs(fy - head_x) < 250 and abs(throw[0]) > 0   # FCU on an x-facing plane near head wall
near_span = not (fx1 < bx[1] - 600 or fx0 > bx[3] + 600)
check("A4-2 R-UX-2 not-above-headboard", not (same_wall and near_span),
      f"fcu face {fy:.0f} vs head wall {head_x:.0f}; {'on head wall over bed' if same_wall and near_span else 'not on head wall'}")

miss = [r["id"] for r in RULES if not r["rule"].startswith("ADVISORY") and not r.get("provenance")]
check("A4-3 provenance", not miss, f"rules missing provenance: {miss or 'none'}")

passed = all(r["pass"] for r in R)
json.dump({"gate": "A4-UX", "pass": passed, "checks": R}, open(OUT / "audits" / "a4_report.json", "w"), indent=1)
for r in R: print(("PASS " if r["pass"] else "FAIL "), r["rule"], "—", r["detail"])
print("=> A4", "ALL PASS" if passed else "FAILED")
sys.exit(0 if passed else 1)
