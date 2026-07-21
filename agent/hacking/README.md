# agent/hacking — HDB hacking / build-wall 产品模块

从 pj-audit-0717 三轮实战（6 个验证案例，audit 全绿）产品化。配套 workflow 在
`.claude/skills/reno-hack/SKILL.md`（三种模式：goal-driven / image-marked / build-wall round）。

## 组成

| 文件 | 职责 |
|---|---|
| `hacking_rules.json` | **规则即数据**（同 `agent/factlayer/hdb_rules.json` 范式）：三道闸（结构/MEP/湿区法规）、permit 判定表、报批图配色规范、界面最大化/严格子线段/门冲突语义、构件规范（推拉门每扇≥700mm、半墙~1100mm）、pipeline 工程坑 |
| `gates.py` | G1-G5 合理性闸 + surgical edit 出图。输入 hack_plan.json + 底图，输出 hacked 图 + validation 报告，exit 0=全过 |
| `cross_audit.py` | R19a-e 交叉验证（hack 衍生事实层 vs 源事实层）：柱并集/窗守恒/未动房间±1.5sqft/面积预算 Δ∈[-(砌墙脚印+2), 拆墙脚印+2]/柜位带继承 |
| `clean_plan.py` | build-wall round 干净底图（拆除白化 + 建议墙浅灰线圈号 + 分级 caption：灰=建议级三选一 / 红=法规级必须围合） |
| `submission_plan.py` | HDB 报批式定稿图（红=拆 / 蓝=砌 / 黄=同位拆建自动判 + legend + notes） |

## 交互 flow（loop 1 已验证闭环）

```
用户目标/打叉图 → 三道闸逐段判定(✅/❌/⚠️/🔴) → gates.py 过闸 → factlayer 重跑+audit+R19
  → clean_plan.py 干净底图交用户 → 用户手画砌墙线段(可改画围合线/携带增量hack)
  → 重跑定稿 → submission_plan.py 报批图(ID 直接对照提交 HDB)
```

## hack_plan.json schema

```json
{
  "goal": "...",
  "removed_segments": [{"rect": [x0,y0,x1,y1], "wall": "描述+⚠️MEP/🔴法规标记", "run_mm": 0}],
  "built_segments":   [{"rect": [x0,y0,x1,y1], "wall": "...", "run_mm": 0, "wall_type": "half-height ~1100mm lightweight"}],
  "doors_preserved":  [[x0,y0,x1,y1]],
  "interface_zones":  [[x0,y0,x1,y1]],
  "kept": "...", "note": "..."
}
```

## 验证案例（回归基准，工作目录 pj-audit-0717/gen-test2-hacking/）

3qr-mbr · 5room-mbr · 4room-living · 5room-suite · 4room-br23 · 3qr-open · 5room-final ·
4room-final · 3qr-final — 全部 G1-G5 过闸 + audit GREEN + R19 ALL PASS。
