#!/usr/bin/env python3
"""HDB submission plan v2 — 报批专用图 (data-complete, audit-gated). Generic CLI.

Three-image deliverable per case (loop-1 architecture):
  1. base-fact plan — as-proposed updated floorplan (hacked+built, no colour) = new baseline
  2. THIS — HDB submission plan: ONLY approval-scope items (demolition + approval-bound
     rebuilds e.g. wet-area enclosure). Every item gets an on-plan leader label (W*/N*)
     and a wall-schedule row (位置/类型/长度mm/厚度mm/动作) + per-item施工条件.
     Permit-free erections (HDB Walls table: hollow block/glass block/gypsum = No)
     are EXCLUDED from the plan and listed in one 免审批 note line.
  3. factlayer roommap — decomposition (pipeline asset)

schedule.json (per case):
  {"unit": "...", "scale_mm_per_px": 17.05, "crop": [x0,y0,x1,y1]?,
   "removed": [{"id":"W1","between":"A | B","type":"非承重砖隔墙","wet":false,"door":false}, ...]  # index-aligned with hack_plan.removed_segments
   "built_bound": {"0": {"id":"N1","between":"...","type":"...","wet":true,"note":"围合条件墙..."}},
   "excluded_note": "免审批项(不在本申请范围): ..."}

Usage:
  python3 submission_plan.py --plan hack_plan.json --schedule schedule.json \
      --image floorplan.png --out sub.png --manifest-out manifest.json
Thickness is MEASURED from plan ink (short-axis band extent, mid 60% of span).
Validate the manifest with submission_audit.py before publishing.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]
RED, BLUE = (214, 40, 40), (35, 80, 210)
COND_STD = "拆至RC梁/板底; 自上而下; 遇钢筋停工报HDB"
COND_WET = "湿区: 防水整体重做+墙面上翻(淋浴≥1800/其余≥300mm) PUB持证"


def font(sz):
    for f in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            continue
    return ImageFont.load_default()


def measure_thickness(gray, rect, scale):
    x0, y0, x1, y1 = rect
    horiz = (x1 - x0) >= (y1 - y0)
    ink = (gray[y0:y1, x0:x1] < 160)
    if horiz:
        lo, hi = int((x1 - x0) * 0.2), int((x1 - x0) * 0.8)
        band = ink[:, lo:hi].mean(axis=1)
    else:
        lo, hi = int((y1 - y0) * 0.2), int((y1 - y0) * 0.8)
        band = ink[lo:hi, :].mean(axis=0)
    idx = np.where(band >= 0.3)[0]
    return None if len(idx) == 0 else round(float(idx[-1] - idx[0] + 1) * scale)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--schedule", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--manifest-out", required=True)
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text())
    cfg = json.loads(Path(a.schedule).read_text())
    sc = cfg["scale_mm_per_px"]
    gray = cv2.imread(a.image, cv2.IMREAD_GRAYSCALE)
    img = cv2.imread(a.image, cv2.IMREAD_COLOR)
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).convert("RGBA")
    ov = Image.new("RGBA", pil.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)
    f_id = font(22)
    items = []
    for i, seg in enumerate(plan["removed_segments"]):
        meta = cfg["removed"][i]
        r = seg["rect"]
        dr.rectangle([r[0], r[1], r[2] - 1, r[3] - 1], fill=RED + (95,), outline=RED + (230,))
        horiz = (r[2] - r[0]) >= (r[3] - r[1])
        lx, ly = (r[2] + 8, (r[1] + r[3]) // 2 - 12) if not horiz else ((r[0] + r[2]) // 2 - 14, r[1] - 26)
        dr.text((lx, ly), meta["id"], font=f_id, fill=RED + (255,))
        th = None if meta.get("door") else measure_thickness(gray, r, sc)
        items.append({"id": meta["id"], "action": "demolish", "rect": r, "run_mm": seg["run_mm"],
                      "thickness_mm": th, "wall_type": meta["type"], "between": meta["between"],
                      "wet": meta["wet"], "door": meta.get("door", False),
                      "conditions": (COND_WET if meta["wet"] else COND_STD)})
    bound = {int(k): v for k, v in cfg.get("built_bound", {}).items()}
    for i, seg in enumerate(plan.get("built_segments", [])):
        if i not in bound:
            continue
        meta = bound[i]
        r = seg["rect"]
        dr.rectangle([r[0], r[1], r[2] - 1, r[3] - 1], fill=BLUE + (140,), outline=BLUE + (255,))
        dr.text(((r[0] + r[2]) // 2 - 14, r[1] - 26), meta["id"], font=f_id, fill=BLUE + (255,))
        items.append({"id": meta["id"], "action": "erect-bound", "rect": r, "run_mm": seg["run_mm"],
                      "thickness_mm": round(min(r[2] - r[0], r[3] - r[1]) * sc),
                      "wall_type": meta["type"], "between": meta["between"], "wet": meta["wet"],
                      "door": False, "conditions": meta["note"]})
    pil = Image.alpha_composite(pil, ov).convert("RGB")
    if cfg.get("crop"):
        pil = pil.crop(cfg["crop"])

    f_t, f_h, f_r = font(24), font(17), font(16)
    W, H = pil.size
    rows = [[it["id"], it["between"], it["wall_type"], str(it["run_mm"]),
             "-" if it["thickness_mm"] is None else str(it["thickness_mm"]),
             "拆除" if it["action"] == "demolish" else "新建(条件墙)"] for it in items]
    cond_lines = [f"{it['id']}: {it['conditions']}" for it in items]
    head = ["编号", "位置(两侧空间)", "墙体类型", "长度mm", "厚度mm", "动作"]
    pad, lh = 16, 26
    n_lines = 4 + len(rows) + 1 + len(cond_lines) + 4
    canvas = Image.new("RGB", (W, H + pad * 2 + 30 + n_lines * lh), (255, 255, 255))
    canvas.paste(pil, (0, 0))
    dc = ImageDraw.Draw(canvas)
    dc.line([(0, H + 1), (W, H + 1)], fill=(220, 220, 220), width=1)
    y = H + pad
    dc.text((pad, y), "PROPOSED RENOVATION — HDB SUBMISSION (审批项清单)", font=f_t, fill=(30, 30, 30)); y += 32
    dc.text((pad, y), cfg["unit"] + " · 尺寸mm · 底图=开发商户型图(非1:1)", font=f_r, fill=(90, 90, 90)); y += lh
    dc.rectangle([pad, y + 4, pad + 26, y + 16], fill=RED)
    dc.text((pad + 34, y), "红=申请拆除", font=f_r, fill=(60, 60, 60))
    dc.rectangle([pad + 170, y + 4, pad + 196, y + 16], fill=BLUE)
    dc.text((pad + 204, y), "蓝=审批包内条件性新建(湿区围合)", font=f_r, fill=(60, 60, 60)); y += lh + 4
    colw = [56, int(W * 0.30), int(W * 0.27), 76, 76, 110]
    x = pad
    for j, htxt in enumerate(head):
        dc.text((x, y), htxt, font=f_h, fill=(30, 30, 30)); x += colw[j]
    y += lh
    dc.line([(pad, y - 4), (W - pad, y - 4)], fill=(180, 180, 180), width=1)
    for row in rows:
        x = pad
        for j, cell in enumerate(row):
            cw = colw[j] - 8
            while cell and dc.textlength(cell, font=f_r) > cw:
                cell = cell[:-1]
            dc.text((x, y), cell, font=f_r, fill=(70, 70, 70)); x += colw[j]
        y += lh
    y += 6
    dc.text((pad, y), "施工条件:", font=f_h, fill=(30, 30, 30)); y += lh
    for line in cond_lines:
        dc.text((pad, y), line[:96], font=f_r, fill=(110, 110, 110)); y += lh
    y += 4
    dc.text((pad, y), cfg["excluded_note"][:96], font=f_r, fill=(140, 140, 140)); y += lh
    dc.text((pad, y), "全部拆除仅限非承重构件; 黑色RC结构/剪力墙/Shelter/立面不动; 梁下现场复核.", font=f_r, fill=(140, 140, 140))
    canvas.save(a.out)
    manifest = {"unit": cfg["unit"], "scale_mm_per_px": sc, "legend": True, "title": True,
                "dims_note": True, "items": items, "excluded_note": cfg["excluded_note"],
                "excluded_built_idx": [i for i in range(len(plan.get("built_segments", []))) if i not in bound]}
    Path(a.manifest_out).write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"{a.out}: {canvas.size}, items={len(items)}")


if __name__ == "__main__":
    main()
