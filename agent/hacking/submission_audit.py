#!/usr/bin/env python3
"""S-gate audit for HDB submission plans — data-completeness gate (generic CLI).

Motivation: real submissions get bounced for missing data (wall dimensions/type),
stalling hacking approval for weeks. This gate blocks publishing an underspecified plan.

  S1 data-complete: every item has id/between/wall_type/run_mm and thickness_mm
     (unless door/opening); run_mm within 15%+40mm of rect long-axis * scale
  S2 scope-exact: every removed_segment appears exactly once; permit-free erections
     never leak onto the plan (excluded_built_idx ∪ bound == all built_segments)
  S3 presentation: legend + title + dims note + unit field present
  S4 wet items carry waterproofing/re-enclosure wording in conditions
  S5 ids unique; W* = demolish, N* = erect-bound

Usage: python3 submission_audit.py --manifest m.json --plan hack_plan.json
Exit 0 = pass.
"""
import argparse
import json
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--plan", required=True)
    a = ap.parse_args()
    man = json.loads(Path(a.manifest).read_text())
    plan = json.loads(Path(a.plan).read_text())
    L, ok = [f"== submission audit: {a.manifest} =="], True
    items = man["items"]
    bad = []
    for it in items:
        if any(v in (None, "") for v in [it.get("id"), it.get("between"), it.get("wall_type"), it.get("run_mm")]):
            bad.append(it.get("id"))
        if not it.get("door") and it.get("thickness_mm") in (None, 0):
            bad.append(f"{it['id']}:thickness")
        r = it["rect"]
        expect = max(r[2] - r[0], r[3] - r[1]) * man["scale_mm_per_px"]
        if abs(it["run_mm"] - expect) > 0.15 * expect + 40:
            bad.append(f"{it['id']}:run_mm {it['run_mm']} vs rect {expect:.0f}")
    ok &= not bad
    L.append(f"S1 {'PASS' if not bad else 'FAIL'} 数据完整(编号/位置/类型/长度/厚度): {bad or 'ok'}")
    dem = [it for it in items if it["action"] == "demolish"]
    g = len(dem) == len(plan["removed_segments"]) and \
        all(any(it["rect"] == s["rect"] for it in dem) for s in plan["removed_segments"])
    bound = [it for it in items if it["action"] == "erect-bound"]
    n_built = len(plan.get("built_segments", []))
    g2 = len(man["excluded_built_idx"]) + len(bound) == n_built
    ok &= g and g2
    L.append(f"S2 {'PASS' if g and g2 else 'FAIL'} 范围精确: 拆除 {len(dem)}/{len(plan['removed_segments'])}; "
             f"新建 {n_built} = 免审排除 {len(man['excluded_built_idx'])} + 条件墙 {len(bound)}")
    g = bool(man.get("legend") and man.get("title") and man.get("dims_note") and man.get("unit"))
    ok &= g
    L.append(f"S3 {'PASS' if g else 'FAIL'} 图面要件: legend/title/尺寸说明/单位栏")
    wet_bad = [it["id"] for it in items if it["wet"] and not any(k in str(it["conditions"]) for k in ("防水", "围合"))]
    ok &= not wet_bad
    L.append(f"S4 {'PASS' if not wet_bad else 'FAIL'} 湿区条款: {wet_bad or 'ok'}")
    ids = [it["id"] for it in items]
    g = len(ids) == len(set(ids)) and all(
        (it["id"].startswith("W") if it["action"] == "demolish" else it["id"].startswith("N")) for it in items)
    ok &= g
    L.append(f"S5 {'PASS' if g else 'FAIL'} 编号唯一且 W=拆/N=条件建")
    L.append("=> SUBMISSION AUDIT PASS" if ok else "=> SUBMISSION AUDIT FAILED")
    print("\n".join(L))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
