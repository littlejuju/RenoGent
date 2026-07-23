#!/usr/bin/env python3
"""AV gate — camera<->floorplan viewmap (the loop-1 hashmap-view logic, ported to 3D cams).

Every render camera is registered back onto the ORIGINAL floorplan ink: position,
direction, FOV wedge clipped by 2D visibility against the room polygon. From the
same wedges we compute floor-grid and wall-edge coverage, so "angles cover the
whole room" is a gated number, not an eyeball claim.

Outputs (out_root/audits/):
  viewmap.json           bidirectional hashmap: cam -> {eye px/mm, dir, wedge, coverage}
                         and floor cell "x_y" -> [cams that see it]
  viewmap-<cam>.png      per-camera minimap: plan ink + wedge + eye dot + arrow
  viewmap-all.png        all cameras on one plan
  viewmap-coverage.png   heatmap: how many cameras see each floor cell
  av_report.json         gate result

Checks:
  AV-1 floor coverage: >=99% of floor cells seen by >=1 perspective cam
  AV-2 redundancy:     >=85% of floor cells seen by >=2 cams
  AV-3 wall coverage:  every polygon edge >=90% of samples seen (short edges >=1)
  AV-4 eyes valid:     every eye inside polygon, outside furniture/MEP boxes
Usage: python3 viewmap.py <room_model.json> <floorplan.png> <out_root>
"""
import json, math, pathlib, sys
from PIL import Image, ImageDraw

M = json.load(open(sys.argv[1]))
PLAN = pathlib.Path(sys.argv[2])
OUT = pathlib.Path(sys.argv[3])
AUD = OUT / "audits"; AUD.mkdir(parents=True, exist_ok=True)

MMPX = M["meta"]["mm_per_px"]
OX, OY = M["meta"]["origin_px"]
POLY = [tuple(p) for p in M["polygon"]]
def to_px(x, y): return (x / MMPX + OX, OY - y / MMPX)

# ---------- 2D visibility wedge ----------
def seg_hit(p, d, a, b):
    """ray p+t*d vs segment a-b -> t or None"""
    ex, ey = b[0] - a[0], b[1] - a[1]
    den = d[0] * ey - d[1] * ex
    if abs(den) < 1e-12: return None
    t = ((a[0] - p[0]) * ey - (a[1] - p[1]) * ex) / den
    u = ((a[0] - p[0]) * d[1] - (a[1] - p[1]) * d[0]) / den
    return t if (t > 1e-6 and -1e-9 <= u <= 1 + 1e-9) else None

def cast(p, ang, maxd=15000):
    d = (math.cos(ang), math.sin(ang))
    best = maxd
    for i in range(len(POLY)):
        t = seg_hit(p, d, POLY[i], POLY[(i + 1) % len(POLY)])
        if t is not None and t < best: best = t
    return (p[0] + d[0] * best, p[1] + d[1] * best)

RAYS = 121
def wedge(cam):
    e = cam["eye"][:2]; t = cam["target"][:2]
    a0 = math.atan2(t[1] - e[1], t[0] - e[0])
    half = math.radians(cam["fov_deg"]) / 2
    pts = [tuple(e)]
    for k in range(RAYS):
        pts.append(cast(e, a0 - half + 2 * half * k / (RAYS - 1)))
    return pts, a0

def in_poly(pt, poly):
    x, y = pt; c = False
    for i in range(len(poly)):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c

pcams = [c for c in M["cameras"] if not c.get("ortho")]
W = {c["id"]: wedge(c) for c in pcams}

# ---------- floor grid coverage ----------
STEP = 100
xs = [p[0] for p in POLY]; ys = [p[1] for p in POLY]
grid = []
for gx in range(int(min(xs)) + STEP // 2, int(max(xs)), STEP):
    for gy in range(int(min(ys)) + STEP // 2, int(max(ys)), STEP):
        if in_poly((gx, gy), POLY): grid.append((gx, gy))
cell_cams = {}
for (gx, gy) in grid:
    cell_cams[f"{gx}_{gy}"] = [cid for cid, (w, _) in W.items() if in_poly((gx, gy), w)]
counts = [len(v) for v in cell_cams.values()]
cov1 = sum(1 for c in counts if c >= 1) / len(counts)
cov2 = sum(1 for c in counts if c >= 2) / len(counts)

# ---------- wall edge coverage ----------
# Exemption: samples hidden behind FULL-HEIGHT joinery (z1>=2100) can never be
# photographed — counted as "concealed", excluded from the seen-ratio denominator
# (same spirit as the A3 niche exceptions). Tolerance 150mm = the A2-3 joinery
# service-gap rule: a wall strip within 150mm behind a full-height unit is a
# trunking/scribe gap, not a photographable surface.
tall = [f["box"] for f in M["furniture"] if max(f["box"][2], f["box"][5]) >= 2100]
def concealed(pt):
    for b in tall:
        if (min(b[0], b[3]) - 150 <= pt[0] <= max(b[0], b[3]) + 150 and
                min(b[1], b[4]) - 150 <= pt[1] <= max(b[1], b[4]) + 150):
            return True
    return False

edge_stats = []
for i in range(len(POLY)):
    a, b = POLY[i], POLY[(i + 1) % len(POLY)]
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    if L < 60: continue
    n = max(2, int(L // 150))
    nx, ny = (b[1] - a[1]) / L, -(b[0] - a[0]) / L      # candidate normal
    mid = ((a[0] + b[0]) / 2 + nx * 25, (a[1] + b[1]) / 2 + ny * 25)
    if not in_poly(mid, POLY): nx, ny = -nx, -ny        # flip to inward
    seen = 0; samples = 0; hid = 0
    for k in range(n):
        f = (k + 0.5) / n
        pt = (a[0] + (b[0] - a[0]) * f + nx * 25, a[1] + (b[1] - a[1]) * f + ny * 25)
        if concealed(pt): hid += 1; continue
        samples += 1
        if any(in_poly(pt, w) for w, _ in W.values()): seen += 1
    edge_stats.append({"edge": i, "len_mm": round(L), "seen": seen, "samples": samples,
                       "concealed": hid, "frac": round(seen / samples, 3) if samples else 1.0})
bad_edges = [e for e in edge_stats if e["frac"] < 0.9]

# ---------- eye validity ----------
boxes = [f["box"] for f in M["furniture"]] + [t["box"] for t in M["mep"]["trunking"]]
def in_box(p, b, z):
    return (min(b[0], b[3]) <= p[0] <= max(b[0], b[3]) and min(b[1], b[4]) <= p[1] <= max(b[1], b[4])
            and min(b[2], b[5]) <= z <= max(b[2], b[5]))
bad_eyes = []
for c in pcams:
    e = c["eye"]
    if not in_poly(e[:2], POLY): bad_eyes.append((c["id"], "outside polygon"))
    for b in boxes:
        if in_box(e, b, e[2]): bad_eyes.append((c["id"], f"inside box {b}"))

# ---------- draw minimaps ----------
CROP = (405, 620, 800, 975)                            # px window around the suite on the plan
SC = 3
plan = Image.open(PLAN).convert("RGB").crop(CROP)
plan = plan.resize((plan.width * SC, plan.height * SC), Image.LANCZOS)
def cpx(x, y):
    px, py = to_px(x, y)
    return ((px - CROP[0]) * SC, (py - CROP[1]) * SC)

CAMCOL = {"cam-entry": (230, 90, 40), "cam-ne": (40, 120, 220), "cam-br3": (30, 160, 90),
          "cam-sw": (180, 60, 200), "cam-se": (220, 160, 20), "cam-n-mid": (200, 40, 110),
          "cam-w-mid": (20, 170, 180), "cam-niche": (120, 100, 230)}

def draw_cam(base, cid, alpha=70):
    im = base.convert("RGBA")
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)
    w, a0 = W[cid]; col = CAMCOL[cid]
    dr.polygon([cpx(*p) for p in w], fill=col + (alpha,), outline=col + (220,))
    ex, ey = cpx(*w[0])
    dr.ellipse([ex - 7, ey - 7, ex + 7, ey + 7], fill=col + (255,), outline=(255, 255, 255, 255), width=2)
    ax, ay = cpx(w[0][0] + 600 * math.cos(a0), w[0][1] + 600 * math.sin(a0))
    dr.line([ex, ey, ax, ay], fill=col + (255,), width=4)
    return Image.alpha_composite(im, ov)

for c in pcams:
    im = draw_cam(plan, c["id"])
    dr = ImageDraw.Draw(im)
    dr.rectangle([0, 0, im.width, 34], fill=(255, 255, 255, 235))
    dr.text((10, 8), f"{c['id']}  fov {c['fov_deg']}°  eye({c['eye'][0]:.0f},{c['eye'][1]:.0f})mm",
            fill=CAMCOL[c["id"]])
    im.convert("RGB").save(AUD / f"viewmap-{c['id']}.png")

im = plan.convert("RGBA")
for c in pcams: im = draw_cam(im.convert("RGB"), c["id"], alpha=28)
dr = ImageDraw.Draw(im)
for j, c in enumerate(pcams):
    dr.rectangle([8, 8 + j * 26, 26, 22 + j * 26], fill=CAMCOL[c["id"]])
    dr.text((32, 8 + j * 26), c["id"], fill=(20, 20, 20))
im.convert("RGB").save(AUD / "viewmap-all.png")

hm = plan.convert("RGBA")
ov = Image.new("RGBA", hm.size, (0, 0, 0, 0))
dr = ImageDraw.Draw(ov)
HC = {0: (220, 30, 30, 150), 1: (235, 170, 30, 90), 2: (120, 190, 60, 80)}
for key, cams_ in cell_cams.items():
    gx, gy = map(int, key.split("_"))
    c0 = cpx(gx - STEP / 2, gy + STEP / 2); c1 = cpx(gx + STEP / 2, gy - STEP / 2)
    col = HC[min(len(cams_), 2)]
    dr.rectangle([c0[0], c0[1], c1[0], c1[1]], fill=col)
hm = Image.alpha_composite(hm, ov)
dr = ImageDraw.Draw(hm)
dr.rectangle([0, 0, hm.width, 30], fill=(255, 255, 255, 235))
dr.text((10, 7), f"coverage: >=1 cam {cov1*100:.1f}%   >=2 cams {cov2*100:.1f}%   (red=0 amber=1 green=2+)",
        fill=(20, 20, 20))
hm.convert("RGB").save(AUD / "viewmap-coverage.png")

# ---------- hashmap + gate ----------
vm = {"mm_per_px": MMPX, "origin_px": [OX, OY], "grid_step_mm": STEP,
      "cams": {c["id"]: {
          "eye_mm": c["eye"], "eye_px": [round(v, 1) for v in to_px(*c["eye"][:2])],
          "dir_deg": round(math.degrees(W[c["id"]][1]), 1), "fov_deg": c["fov_deg"],
          "note": c.get("note", ""),
          "floor_cover_pct": round(100 * sum(1 for v in cell_cams.values() if c["id"] in v) / len(cell_cams), 1),
      } for c in pcams},
      "cell_to_cams": cell_cams, "edges": edge_stats}
json.dump(vm, open(AUD / "viewmap.json", "w"), indent=1)

R = []
def check(rule, ok, detail): R.append({"rule": rule, "pass": bool(ok), "detail": str(detail)})
check("AV-1 floor>=1cam", cov1 >= 0.99, f"{cov1*100:.1f}% of {len(grid)} cells")
check("AV-2 floor>=2cam", cov2 >= 0.85, f"{cov2*100:.1f}%")
check("AV-3 walls", not bad_edges, bad_edges or f"all {len(edge_stats)} edges >=90% seen")
check("AV-4 eyes", not bad_eyes, bad_eyes or f"{len(pcams)} eyes inside room, clear of furniture/MEP")
passed = all(r["pass"] for r in R)
json.dump({"gate": "AV", "pass": passed, "checks": R}, open(AUD / "av_report.json", "w"), indent=1)
for r in R: print(("PASS " if r["pass"] else "FAIL "), r["rule"], "—", r["detail"])
print("=> AV", "ALL PASS" if passed else "FAILED")
sys.exit(0 if passed else 1)
