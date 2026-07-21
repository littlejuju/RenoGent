#!/usr/bin/env python3
"""R19 · hack cross-validation (user-required): a hacking-proposed fact layer is a
DERIVATIVE of the source fact layer — the building's columns/windows/beams must be
untouched and floor gains may come ONLY from the removed wall footprint.

Checks (vs hack_source_facts):
  R19a columns    — facts-level RC node count unchanged (image-level identity is G3)
  R19b windows    — physically unchanged, guaranteed by gate G2 (pixel-identical
                    outside removal rects) + G4 (rects touch no door/window plane);
                    facts-level: total window entries conserved across merge
  R19c rooms      — every room NOT adjacent to a removed/built wall keeps its area (±1.5 sqft)
  R19d budget     — Σroom-area delta ∈ [-(built footprint + 2), removed-wall footprint + 2 sqft]
                    (build-wall rounds ADD walls: delta may be negative, bounded by new-wall ink)
  R19e niches     — cabinet-niche total inherited (loss ≤ 0.6 sqft)
Run inside a hack factlayer-out dir (or pass the dir as argv[1]). Writes R19_report.txt; exit 1 on any FAIL.
"""
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
cfg = json.loads((ROOT / "plan_config.json").read_text())
SC = float(cfg["scale_mm_per_px"])
hacked = json.loads((ROOT / "facts.json").read_text())
source = json.loads((ROOT / cfg["hack_source_facts"]).read_text())
plan = json.loads((ROOT / cfg["hack_plan"]).read_text())
px2 = (SC / 1000) ** 2 * 10.7639

rects = [s["rect"] for s in plan["removed_segments"]]
built_rects = [s["rect"] for s in plan.get("built_segments", [])]
def touches_removed(poly, pad=20):
    for (x0, y0, x1, y1) in rects + built_rects:
        for (px, py) in poly:
            if x0 - pad <= px <= x1 + pad and y0 - pad <= py <= y1 + pad:
                return True
    return False

L, ok = [f"== R19 hack cross-validation vs {cfg['hack_source_facts']} =="], True

# R19a columns — physical identity is G3 (pixel-level); here compare the DEDUPED
# union of declared node coordinates: a node may legitimately change room
# attribution next to the hacked wall, but may not vanish elsewhere.
def col_union(f):
    pts = []
    for r in f["rooms"]:
        for c in r.get("columns", []):
            if not any(abs(c["x"] - q[0]) <= 8 and abs(c["y"] - q[1]) <= 8 for q in pts):
                pts.append((c["x"], c["y"]))
    return pts
us, uh = col_union(source), col_union(hacked)
missing = [q for q in us if not any(abs(q[0] - w[0]) <= 8 and abs(q[1] - w[1]) <= 8 for w in uh)]
bad = [q for q in missing if not any(x0 - 30 <= q[0] <= x1 + 30 and y0 - 30 <= q[1] <= y1 + 30
                                     for (x0, y0, x1, y1) in rects)]
g = not bad
ok &= g
L.append(f"R19a {'PASS' if g else 'FAIL'} 柱/RC节点并集: source {len(us)} -> hacked {len(uh)}, "
         f"拆墙邻域外消失 {len(bad)} 个 {bad[:4]} (物理同一性由 G3 逐像素保证)")

# R19b windows
nw_s = sum(1 for r in source["rooms"] for d in r["doors_windows"] if d["type"].startswith("window"))
nw_h = sum(1 for r in hacked["rooms"] for d in r["doors_windows"] if d["type"].startswith("window"))
g = nw_h >= nw_s - 2  # merged rooms may combine two facade-band entries into one
ok &= g
L.append(f"R19b {'PASS' if g else 'FAIL'} 窗: source {nw_s} 条 -> hacked {nw_h} 条 "
         f"(物理不变由 G2 逐像素闸保证; 合并房允许把同立面两段并记)")

# R19c unchanged rooms
sa = {r["key"]: r for r in source["rooms"]}
ha = {r["key"]: r for r in hacked["rooms"]}
for k in sorted(set(sa) & set(ha)):
    adj = touches_removed(ha[k].get("polygon_px") or [])
    d = abs(ha[k].get("area_sqft", 0) - sa[k].get("area_sqft", 0))
    if adj:
        L.append(f"R19c  --   {k}: 邻接拆除墙, 面积 {sa[k].get('area_sqft')}->{ha[k].get('area_sqft')} (允许变化)")
    else:
        g = d <= 1.5
        ok &= g
        L.append(f"R19c {'PASS' if g else 'FAIL'} {k}: {sa[k].get('area_sqft')} -> {ha[k].get('area_sqft')} (Δ{d:.1f})")
merged_keys = sorted(set(sa) - set(ha))
new_keys = sorted(set(ha) - set(sa))
L.append(f"R19c  合并: {merged_keys} -> {new_keys}")

# R19d budget
tot_s = sum(r.get("area_sqft", 0) for r in source["rooms"])
tot_h = sum(r.get("area_sqft", 0) for r in hacked["rooms"])
wall_fp = sum((x1 - x0) * (y1 - y0) for (x0, y0, x1, y1) in rects) * px2
built_fp = sum((x1 - x0) * (y1 - y0) for (x0, y0, x1, y1) in built_rects) * px2
delta = tot_h - tot_s
g = -(built_fp + 2) <= delta <= wall_fp + 2
ok &= g
L.append(f"R19d {'PASS' if g else 'FAIL'} 面积变化只能来自拆墙/砌墙: Σnet {tot_s} -> {tot_h} "
         f"(Δ{delta:+.1f} sqft) ∈ [-({built_fp:.1f}+2), {wall_fp:.1f}+2]")

# R19e niches
ni_s = sum(r.get("cabinet_niche_sqft", 0) for r in source["rooms"])
ni_h = sum(r.get("cabinet_niche_sqft", 0) for r in hacked["rooms"])
g = ni_h >= ni_s - 0.6
ok &= g
L.append(f"R19e {'PASS' if g else 'FAIL'} 柜位带继承: source {ni_s:.1f} sqft -> hacked {ni_h:.1f} sqft")

L.append(f"=> {'R19 ALL PASS' if ok else 'R19 FAILED'}")
rep = "\n".join(L)
(ROOT / "R19_report.txt").write_text(rep)
print(rep)
sys.exit(0 if ok else 1)
