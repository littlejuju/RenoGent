# Designer v2 — 事实接地的两段式渲染管线

状态：planning（2026-07-16，未开工）
上游输入：用户上传的户型图 + homeowner brief
下游消费者：contractor agent（RFQ/BOQ 用事实层出量）、PJ reviewer agent（审计记录 + 版本历史是它的原料）

---

## 0. 目标与不变式

用户上传户型图后，系统产出「用户逐房间批准的 design pack」，全程 automode，人只做两类动作：**确认/推翻推断**、**批准/否决渲染**。

四条不变式（违反任何一条 = 管线 bug）：

1. **事实先行**：任何渲染动作之前，L1 事实层必须已生成且通过一致性校验。
2. **推断可推翻**：所有规范推断以数据存在（不是 prompt 文本），用户可逐条推翻，**最新版本是唯一 hook**。
3. **结构先于风格**：Stage A（3D 毛坯）审计未通过，Stage B（design 渲染）不解锁。
4. **两类审计不混用**：结构吻合审计（vs 毛坯）与设计原则审计（vs brief/HDB 风格规范）分开跑、分开报告。

---

## 1. 数据层（取代现状的 briefs.json + dimension manifest 双轨）

### L0 — 原图（不可变）
上传的户型图原件 + 预处理裁剪版。只读。

### L1 — 事实层 `facts.json`（度量事实，确定性）
每条事实一个对象，统一 schema：

```json
{
  "id": "wall.living.south.1",
  "kind": "wall | door | window | opening | dim | room_polygon | adjacency | calibration",
  "geometry_px": {...},              // 图上坐标
  "value_mm": 4648,                  // 度量值（若适用）
  "source": "printed | derived_from_scale | user_provided",
  "formula": "px_len * mm_per_px_x", // derived 必填
  "confidence": "high | medium | low",
  "evidence": "crops/wall-living-south-1.png",  // 标注证据图
  "review_required": false
}
```

必须覆盖（这是对 dimension_decompose 的扩展，不只是边长）：
- **标定**：≥2 条印刷尺寸做 mm/px（x/y 各自），交叉验证误差 <1%
- **全部印刷尺寸**（OCR + vision 双读，不一致标 review_required）
- **未标注但可按比例尺推算的尺寸**：全部墙段边长、房间净宽净深
- **门**：位置、开启宽度、开向（弧线符号）
- **窗**：位置、宽度（sill 高度属于 L2 推断，不在此层）
- **墙**：段落坐标 + 厚度（从双线间距量）
- **房间多边形 + 邻接关系**

一致性校验（确定性，不走 LLM）：闭合环校验（一圈墙段长度和 = 外框印刷总尺寸）、对边等长校验、门窗开口必须落在所属墙段上。不通过 → 整层标 review_required，不放行。

### L2 — 推断层 `inferences.json`（规范推断，可推翻）

```json
{
  "id": "window.living.south.type",
  "claim": "标准 HDB 窗带，实心 parapet，sill ≈1.0m（非落地窗）",
  "basis": "hdb_rule:window_parapet",   // 引用规则库条目
  "depends_on": ["window.living.south"], // 依赖的 L1 事实
  "confidence": "high",
  "status": "proposed | user_confirmed | user_overridden",
  "history": [ ... ]                     // 每次改动追加，最新为准
}
```

HDB 规则库 `agent/factlayer/hdb_rules.yaml`（规则即数据，推断引擎逐条应用）：
- 窗型：落地窗仅出现于指定 BTO 批次/公寓化设计，默认 parapet 窗带
- 阳台判定：宽度 <1.5m + 连通厨房/service riser + pass-through 形态 → service hallway 而非 leisure balcony；封闭 + homeowner 命名 → 室内房间（study 教训已验证）
- 梁：外墙沿线、单元分界线、跨度 >4m 的房间中线为候选梁位（HDB 图纸通常不画梁 → 全部 medium confidence，必须用户确认或现场照片佐证）
- 柱：转角单元角部、结构跨度节点
- 水电：wet area（bath/WC/kitchen）沿 service riser 布置立管；天花走线
- 墙体：party wall / 结构墙 = concrete（不可拆），非承重隔墙 = hollow brick/轻质（可拆）——从墙厚 + 位置推断

### L3 — 用户 brief 层 `brief.json`
风格要求 + 硬性 veto（"no grid on window" 类），沿用现有 veto 语义，但落成结构化数据（每条 veto 一个 id），渲染与审计按 id 引用。

### 版本机制
三层文件全部走 event-sourced 追加日志（`facts.log.jsonl`），当前快照由日志重放生成。用户在 console 说「窗户其实是落地窗」→ 生成 override 事件 → 快照更新 → 依赖该事实的下游产物（毛坯、渲染）自动标记 stale，触发重跑。**hook 永远绑定最新快照版本号**，渲染产物记录它所依据的版本号，审计时版本不匹配 = 直接 fail。

---

## 2. Stage A — 2D→3D 毛坯（结构渲染）

**输入**：L1 + L2 最新快照。**产出**：每房间毛坯渲染图（轴测 + 相机透视两版）+ 全屋毛坯。

- 从 facts 的房间多边形挤出墙体（用实测墙厚、2.6m 层高），在实测位置开门窗洞（L2 决定窗型/sill），放置推断的梁柱（medium confidence 的梁柱以半透明 + 标注呈现，等用户确认）。
- 纯确定性绘制（PIL/或升级 three.js headless），**不走图像生成**——现有 render_remaining_whiteboxes.py 的路线是对的，任务是从硬编码改为「由 facts.json 驱动」。
- 相机透视版毛坯的相机参数 = briefs 的 camera_px/look_at_px 换算进 3D 场景 —— 这张图就是 Stage B 的底图。

**Audit A（结构审计，通过才解锁 Stage B）**：
1. 边长审计：毛坯每条边反投影 vs facts 期望值，容差 1.5%（沿用现有 edge-audit，扩展到全部事实）
2. 开洞审计：门窗洞位置/宽度 vs facts
3. 梁柱在位审计：L2 中 user_confirmed 的梁柱必须出现
4. 视锥一致性：透视版毛坯可见组件集合 == briefs expected_components（确定性比对，不再靠 VLM 猜）

全部确定性检查。通过后写 `whitebox-approval.json`（记录事实层版本号），并把毛坯发给用户过目（可跳过等待，automode 下默认放行，用户 veto 再回滚）。

## 3. Stage B — Design 渲染（风格渲染）

**输入**：Stage A 透视毛坯图（底图）+ L3 brief。**关键改动：nano-banana 的 input image 从 2D 户型图换成 3D 毛坯透视图**，配已验证的结构锁定 prompt（"keep exact same walls/windows/ceiling/camera"）。这正是 hackathon 验证过的最强配方（11s/$0.04），此前只是没接进主链。

**Audit B（两个独立审计，分开报告）**：
- **B1 结构吻合审计（fatal）**：design 渲染 vs 毛坯底图逐组件比对——墙面数量/位置、门窗洞、梁柱、相机角，任何偏差 = quarantine。VLM 比对 + 现有 meta-audit 防审计幻觉。（取代现有 L1/L2 对 2D 图的审计——比对两张同视角 3D 图远比"3D 渲染 vs 2D 平面图"可靠。）
- **B2 设计原则审计**：veto 逐条核查（按 id）、HDB 风格规范（L3 style 类）、brief 指定材质颜色。B2-only 违规 → 沿用现有 escalation 语义（带图上报人审，品味归人）。

重试策略沿用 render_all 现有的 bounded escalation（2 base × 2 fix + plateau early-exit），但 surgical fix 的底图始终带毛坯参照。

## 4. 交付物（给下游 agent 的接口）

designer 步骤结束时产出 `design-pack/`：
- `facts.json` / `inferences.json` 最终快照（contractor agent 出 BOQ/RFQ 的量数据源）
- 每房间：批准的 design 渲染 + 对应毛坯 + Audit A/B 报告
- `decisions.jsonl`：用户全部确认/推翻/veto 记录（PJ reviewer agent 的问责原料）

## 5. 工作包与顺序

| WP | 内容 | 验收标准 |
|----|------|---------|
| WP0 | 数据 schema + event log + 快照重放 + stale 传播 | demo 图的现有 manifest/briefs 迁移进新 schema，override 一条事实能触发下游 stale |
| WP1 | 事实提取器：vision 提案 → 确定性校验闭环（标定/OCR/推算/门窗/墙厚） | demo 图全自动重建 facts.json，与 Codex 硬编码版本误差 <1.5%；换第二张 HDB 图可跑通 |
| WP2 | HDB 规则库 + 推断引擎 | demo 图产出全部 L2 条目；study/阳台历史翻车 case 判对 |
| WP3 | 毛坯 builder 事实驱动化 + 透视相机版 | 全屋毛坯由 facts.json 生成（删掉硬编码坐标），Audit A 全过 |
| WP4 | Stage B 改底图 + B1/B2 审计拆分 | 同一房间：新链路渲染结构违规率显著低于旧链路（用 render-audit-log 对比） |
| WP5 | 用户更新回路（console 命令 → override 事件 → 重跑受影响房间） | 「living 的窗是落地窗」一句话触发 living 毛坯+渲染重做，其他房间不动 |

依赖链：WP0 → WP1/WP2（可并行）→ WP3 → WP4 → WP5。WP1 是最大风险项（vision 度量提取的可靠性），策略是「vision 只做提案，确定性几何校验做裁判」，校验不过就 review_required 降级人审，不硬猜。

## 6. 已知风险

- **毛坯→nano-banana 漂移**：风格化可能改几何。缓解：结构锁定 prompt 已验证 + B1 审计兜底 + 必要时叠 depth/edge control（flux-depth 丢房间身份的教训 → 只作为备选，不作默认）。
- **梁柱无图纸依据**:HDB 平面图不画梁 → L2 推断永远 medium，必须走用户确认/现场照片，渲染中未确认梁柱不画（宁缺勿错）。
- **OCR 印刷尺寸**：小字/密集标注误读 → 双读不一致即 review_required，绝不静默采用。
