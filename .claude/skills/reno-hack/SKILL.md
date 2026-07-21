---
name: reno-hack
description: RenoGent HDB 户型 hacking 提案器 — 输入目标(砸墙扩房/合并房间)或打叉标注图, 输出 surgical edit 后 audit 全绿的 hacking proposed fact layer + 标注图。三种模式:goal-driven / image-marked / build-wall round(hack 后干净底图交用户决策砌墙, 定稿出 HDB 报批式图)。
---

# reno-hack · HDB 户型 hacking 提案 workflow

对一个**已有 fact layer**(audit GREEN)的户型, 生成 hacking proposed 版本:
surgical edit 图纸 → 合理性闸 → 重跑 factlayer pipeline → audit R1-R18 + R19 交叉验证 → 总览+标注图。
**任何 hack 输出都是 PROPOSED(拟改), 不是现状; 落地需 HDB permit + 梁下现场复核。**

## 前置条件

- 源户型已有完整 factlayer 工作目录(`plan_config.json` + `facts.json` + `room_seeds.json` + audit GREEN)。
  参考实现: `~/Documents/Claude/Projects/reno-advocate/pj-audit-0717/`
  - 原图: `factlayer-out/`(3QR v12) · 泛化图: `gen-test/{5room,4room}/factlayer-out/`
  - hack 工具: `gen-test2-hacking/make_hacks.py`(surgical edit + G1-G5) · `gen-test2-hacking/audit_hack_cross.py`(R19)
    · `make_clean_plans.py`(build-wall 干净底图交付) · `make_submission_plans.py`(HDB 报批式定稿图)
- 没有 fact layer 的新图 → 先走 factlayer 泛化流程(标定→seeds→trace→facts→audit), 再回来。

## 两种输入模式

### 模式 1 · goal-driven(用户说目标, 我评估每个子墙段)

用户输入例: "砸卧室扩充 living room" / "合并 bed1 和 bed3" / "主卧做套房"。

1. **列候选墙段**: 从 facts.json 的 walls + polygon 邻接关系, 找出目标房间之间/周边的**每一个子墙段**
   (一面墙 ≠ 一个决策单位; 按 门洞/门垛/柱/交接点 切成子段, 逐段判断)。
2. **逐段判 can-hack**(硬约束, 任一不过即该段不可拆):
   - ❌ 黑色实体墨 = RC 结构墙/剪力墙(BTO 图例明文"shall not be hacked")
   - ❌ 段内或紧邻有 detect_columns 检出的柱/RC 节点
   - ❌ Household Shelter 任何一面墙(全 RC, 永不可动)
   - ❌ 外立面墙(动窗 = 违反"窗户位置不变"硬规)
   - ❌ 段上骑着要保留的门(门框/门垛零相交, G4)
   - ⚠️ 1970s 砖隔墙(细双线~100-170mm)可 hack 但需 permit; 梁下要现场复核
2b. **逐段判 MEP**(非承重≠能拆, 管线是第二道闸):
   - ❌ **污水立管墙**: 立管(soil stack)所在墙段不可拆; 立管位从 WC pan 位置反推(pan 贴哪个角,
     立管就在那个角, 常为黑RC外墙/party wall 角) — pan 也不得远离立管(位移需 HDB 特批)
   - ⚠️ **给水/电**: 湿区隔墙常承龙头/花洒/热水器给水与电点 — 可拆但需改道, 现场核对走管
   - ⚠️ **燃气**: 厨房墙(尤其灶位沿墙)拆除涉及燃气支管改道, 须 City Gas 持证工人
   - ✅ **管线墙优先保留**: 水槽/器具靠着的墙(供排水立面)尽量列入 kept — 3qr-open 案例:
     BATH-厨房分隔墙因水槽管线整面保留
2c. **湿区法规红灯**(可拆 ≠ 拆完成立 — 触发即在 plan 里给 rebuild suggestion):
   - 🔴 **围合**: HDB 要求卫生间必须围合(墙+门) — 湿区外围墙拆除后**必须重砌围合**
     (built_segments 原线/新线重建 + 新门, 如 3qr-open B1/B2+单门替代两门), 全拆不砌 = 方案不成立
   - 🔴 **防水**: 拆湿区墙/动地面即破坏防水层 — 地面防水整体重做 + 墙面上翻
     (淋浴墙 ≥1800mm, 其余 ≥300mm 常规), PUB 持证水工; facts 的 mep claim 必须写明
   - 🔴 **楼龄**: <3年新 BTO 禁拆湿区墙/地(防水保修期) — 老房不适用但要记录判定
   - 输出格式: 每个湿区拆除段的 wall 描述里带 ⚠️MEP/🔴法规 标记, overview 加"湿区法规红灯"一节
3. **逐段判 should-hack**(合理性):
   - **目标界面"能拆都拆"(G5 maximal)**: 被合并/打开的两个空间之间的界面上, 所有过 can-hack 的段
     **全部拆除**(含门, 见门规则) — 只拆一段留其余是不合格方案(4room v3 教训, 被用户退回);
     G5 闸自动验证: 界面区内 hack 后只允许剩 RC/柱/用户勾选保留的门
   - **非目标界面最小干预**: 与目标无关的墙一律不动
   - 每个**保留下来的封闭房间**门都还在(拆到门垛为止)
   - 不留"半岛墙梢"刺进合并空间(R13 会抓)
   - circulation 不消失(R2)、不产生无归属孤区(R16 — 全开界面用**真合并单房**建模,
     开放 zone+virtual 记账会留 burn 宽度的无主条带)
   - 拆除段两端**收口位置写明**(到哪个门垛/交接点/柱边)
4. **门冲突规则**(两种模式通用):
   - 界面上的门默认随界面拆除; 其他受影响的门逐个列出问用户(或用户已在图上 ✓/✗)
   - **✓ 保留**: 门+门垛计入 kept, G4 保证拆除矩形零相交
   - **✗ 不保留**: skill 按 **goal + enclosure** 判两种处理:
     * goal=开放/合并 且并入后无私密需求 → **open area**(门整体拆除, 不砌墙; 4room BR3 门案例)
     * 并入后剩余房间仍需封闭(如套房吞走廊门后卧室失去 enclosure) → **砌墙**(make_hacks
       `built_segments` 画新隔墙双线; G2 同样豁免声明矩形, 新墙不得压门/窗/柱)
5. 产出 hack plan: removed_segments + built_segments + kept + doors 决策 + interface_zones + 备注。

### 模式 2 · image-marked(用户图上标注, 我判可不可拆)

用户输入例: 在 roommap/原图截图上手画 ✗ 或线条标记要拆的**墙段**; 在**门区域**打 ✓(保留)/✗(不保留)。

1. **定位标记**: 对比标注图 vs 干净底图(颜色差/红色笔画检测), 把每个 ✗/线条映射到**具体子墙段**
   (吸附到最近的墙段 ink; 说不清就贴回截图问用户确认段的两端)。
   **⚠️严格子线段映射**: ✗ 只作用于被标记的那个子段, **禁止顺势外推到未标记的相邻墙段**
   ("能拆都拆"只适用于 goal 界面判定, 不是把✗放大的许可) — 3qr-open 教训: ✗打在nib角上,
   我顺着把未标的 BATH-厨房分隔墙整面拆了, 被用户退回(那面墙是水槽管线墙, 保留)。
   拆除集合定稿后做**连通自洽检查**: 保留段不得因两端邻段被拆而变成孤岛墙/无支承半岛。
2. 对每个标记段跑模式 1 的 **can-hack + 2b MEP + 2c 法规判定**, 逐段回复: ✅可拆(理由) /
   ❌不可拆(哪条硬约束/立管) / ⚠️可拆但需改道(给水/燃气)或调整收口 / 🔴可拆但必须 rebuild(围合+防水 suggestion)。
   **门上的标记**走模式 1 第 4 条门冲突规则: ✗ 的门由我判 砌墙 vs open area(goal+enclosure), 判定结果连同理由回给用户。
3. 全部 ✅/用户确认后 → 直接执行下面的 pipeline 出图。
4. 部分 ❌ → 报告哪些段不能拆及原因, 只拆 ✅ 段(或等用户改标记)。

### 模式 3 · build-wall round(hack 后第二轮交互: 砌墙决策权在用户)

**不是独立 skill** — 与 hack 共用全部机器(built_segments/G2 豁免/pipeline/audit/R19),
是同一个 image-marked loop 的第二轮。hack 案 audit 过后**不直接定稿**:

1. **交付干净底图**(`make_clean_plans.py`): hack 后底图(仅白化拆除段, 不画实体新墙),
   我的建议砌墙段画**非常浅的灰色双线** + ①②圈号, 图下 caption 分级说明:
   - **建议级**(goal 围合, 非法规, 灰字): 用户三选一 — 按建议砌 / 手画自己的线段 / 不砌
   - **🔴法规级**(湿区围合等, 红字"必须"): 可改画别的围合线, 但必须成封闭+门, 不砌方案不成立
   - 手机截图类底图先 crop 掉 chrome; caption 字体 Hiragino Sans GB(✓/🔴 emoji 会豆腐块, 用文字)
2. **用户回手画线段图 / 口头确认 / 选不砌**:
   - 手画线段 → 映射同模式 2 严格子线段规则: 线段吸附墙轴/印刷虚线/门垛; **砌满到实体面**;
     不得压 RC/柱/窗/保留门; 湿区围合红灯重新校验(新围合不封闭即退回重画)
   - **用户可改画围合线取代我的法规红灯方案**(3qr-final: 沿垃圾道北阈值线包整个湿区,
     y811 原线重砌取消) — 只要新围合成封闭+门即成立, 防水范围随围合线扩大(含并入的干区地面)
   - **build round 可携带增量 hack**(3qr-final: 湿区门改厨房侧 → 保留墙上段开门洞 818mm) —
     增量段照走 can-hack/MEP/法规三道闸(管线墙开洞取避让段+现场核对)
   - **未标注的建议墙默认按建议执行**(用户只画新内容=接受建议级方案), 报告里写明
   - **墙型标注**: 半墙(~1100mm 不到顶)/玻璃隔断/推拉门 → hack_plan 加 `wall_type`, 事实层按
     房间围合建模但 area_note 写明 semi-enclosed; **推拉门宽度合理性**: 双扇每扇 ≥700mm,
     用户手画门洞过窄要修正并说明(4room-final 1120→1501mm)
   - 不砌 → 删 built_segments + 恢复该门洞 door burn 语义(开放界面), 说明 enclosure 后果
3. 改 built_segments → 重跑 pipeline(步骤 1 起) → 定稿走步骤 9 报批图。
4. **HDB permit 判定口径**(官方 Walls 表, hdb.gov.sg renovation-guidelines/building-works):
   审批触发项只有**拆除** — 拆任何墙(含轻质隔墙)必须 permit, 非承重RC拆除 permit+PE 监督;
   **砌墙(erection)一律免审批**(63mm空心砖/80mm玻璃砖/gypsum 均 Permit=No, 附采光/逃生/
   lintol/单层/紧固件条件) — 报批清单只列拆除项可缩短评估; 例外: 湿区重围合墙绑定卫生间
   工程包不可剥离(N* 条件墙上图)。新墙默认轻质单层材料。

## 执行 pipeline(三种模式共用)

```
1. surgical edit   在 make_hacks.py 的 HACKS dict 加/改条目(removed_segments/kept/doors_preserved)
                   → python3 make_hacks.py: 白化声明矩形 → 合理性闸 G1-G4:
                   G1 拆除区无 ≥12px 双向厚实体墨(6×6 腐蚀存活=RC)
                   G2 编辑仅限声明矩形(矩形外逐像素相等 → 窗必然不动)
                   G3 detect_columns(hack前)==detect_columns(hack后)
                   G4 保留门/门垛平面与拆除矩形零相交
                   G5 界面最大化: interface_zones 内 hack 后仅剩 RC(6x6腐蚀存活±10px)/勾选保留物, 残留非结构墨 ≤60px
                   (built_segments: 画新隔墙双线; G2 掩码同样豁免)
                   闸不过 → 改 hack plan, 不进入下一步
2. 建工作目录       gen-test2-hacking/<name>/factlayer-out/: 拷源目录全部脚本+config+references+seeds
                   plan_config.json 加: "hack_plan": "../hack_plan.json",
                   "hack_source_facts": "<源facts.json相对路径>"
                   (3QR 源保持 paired_no_wrap/absorb_enclosed_holes=false 钉住 v12 可复现)
3. seeds/facts 适配  界面全开(合并/扩房) → **真合并单房**: 两房 seeds/facts 合并(burns 取并集,
                   niche/柱/窗 必须全额继承!)
                   界面部分开(留了部分墙/门) → 房间保留, 双方共享**同一条全跨** virtual burn
                   (单边跨两个 burn 匹配不上; 两侧各画一条会留无主条带)
                   砌墙(built)后的门洞 → 对应 door burn 删除(已是实体墙)
                   房间串/重叠 → BFS 追泄漏路径(种子→入侵区回溯), 常见缝: 墙端与墙线间 2-3px
                   slit、拆段上方/下方绕行 — 用短 seal 封在保留墙的实体面上
4. 重跑            measure_room(全量! 单房重跑不落盘) → gen_facts/合并脚本 → apply_polygons
                   → assign_columns(⚠️ 3QR 类有手工柱归属的源: 跳过, 从源 facts 继承)
                   → build_assets → build_dimensioned(roommap 自动画红色 HACKED 叉带+外部区灰斜线)
5. audit 循环      audit_factlayer.py 到 exit 0 (R1-R18) — ≤5 次尝试, 还错 → 回头重查 hack plan 本身
6. R19 交叉验证    python3 ../../audit_hack_cross.py (在 hack factlayer-out 内):
                   R19a 柱并集不变(拆墙邻域豁免归属漂移) · R19b 窗守恒(G2兜底)
                   R19c 未动房间面积 ±1.5sqft · R19d Σ面积增量≤拆墙脚印+2sqft · R19e 柜位带全额继承
7. 总览            build_overview.py(audit 不绿会拒绝) + 追加 Hack Plan/G1-G5/R19 三段到 00-overview.md
                   (涉湿区的案例再加"🔴湿区法规红灯"一节: 围合重砌/防水上翻/立管/燃气/楼龄)
8. build-wall 交付  make_clean_plans.py: 干净底图(白化拆除段, 建议墙=浅灰双线+圈号,
                   法规红灯=红字"必须") → 发用户 → 模式 3 决策循环(改 built_segments 回步骤 1)
9. 定稿三图交付     ①base-fact: 更新后户型基础事实图(hacked+built 无色) = 新项目基线;
                   ②HDB 报批专用图(agent/hacking/submission_plan.py): **只含审批项** —
                   拆除段(红,W*编号) + 审批包内条件墙(蓝,N*, 如湿区围合); 每项带墙体数据表
                   (位置/类型/长度mm/厚度mm实测/动作)+施工条件; 免审批新墙(HDB Walls表
                   erection=No: 空心砖/玻璃砖/gypsum)整体不上图, 一行免审批注说明
                   → submission_audit.py S1-S5 数据闸 exit 0 才能发布(防数据不够被退回);
                   ③factlayer roommap 拆解图(pipeline 产物)
10. 发布           lark-cli import 到 "泛化测试二 hacking" 类文件夹 + media-insert roommap
                   (anchor 行 "- 00-roommap.png", --width 620); 用户人工检查 gate
```

## 已验证案例(回归基准)

| 案例 | 类型 | 结果 |
|---|---|---|
| 3qr-mbr | 指定合并 bed1+bed3 | 拆 x591-605 y699-906(至bed1门垛), 套房240sf, R19 全过 |
| 5room-mbr | goal 扩主卧(自拟) | 拆主卧-BR2隔墙 + BR2南墙西段小墙(用户✗补拆, 至主卧门北门垛x399), 套房241sf |
| 4room-living | goal 扩客厅 | v4: 界面能拆都拆 — 南墙1883+东返墙896+门1080mm 全拆(门→open area), BR3真合并入客厅371sf |
| 5room-suite | 模式2 round-2 (3✗+1✓) | 5room-mbr + BR2门✗→**砌墙**(套房围合, built_segments 首用), 主卧门✓唯一入口, 套房241sf |
| 4room-br23 | 模式2 round-2 (2✗+1✓) | BR2/BR3隔墙3187mm✗ + BR2门✗→砌墙 + BR3门✓唯一入口, 真合并大卧194sf |
| 3qr-open | 模式2 round-2 复杂 (8✗+1✓) | v2(用户复核): 两卫合并30sf(隔墙✗拆, 北墙✗拆后🔴原线重砌+单门围合, BATH-厨房分隔墙未标=保留/管线墙); 厨房开放并入客厅339sf(nib+南墙两段✗); BR1/BR3套房240sf(BR3门✗砌墙); ⚠️MEP/🔴防水红灯全标注 |
| 5room-final | 模式3 build-wall | 建议①接受 + study 半墙围合(东2158+南2009mm, ~1100mm轻质)+拐角玻璃门890mm; study 58sf semi-enclosed; R19d Δ+7 |
| 4room-final | 模式3 build-wall | 建议①接受 + 厨房封闭(轻质墙1594mm+双扇推拉门1501mm, 用户1120mm过窄修正); 封闭厨房燃气通风注意 |
| 3qr-final | 模式3 改画围合线+增量hack | 湿区=lobby+WC+BATH整体围合46sf: 北围合墙1859mm新建+分隔墙上段开门818mm(厨房侧入口, 管线墙避让段), y811重砌取消; Σ862 Δ+20 |

## 工程坑(必读 — 判定类规则都已并入上文章节, 这里只留 pipeline 机制坑)

- **文案数据驱动**: 不复制别的图/别的案例的判断进 facts("无窗下柜位"污染 3QR 的教训)。
- **砌墙要砌满**: 门垛墨稀疏(几根短线)挡不住 flood — 新墙直抵邻近隔墙/门垛实体面(5room-suite 首跑套房串进BR3 5.1sqft)。
- **拆墙收口留 G3 领口**: 黑RC块窄于 11px 检测窗时, 检测靠贴脸墙线凑数 — 贴块拆除留 ~250mm 墙领口, 否则 G3 报柱消失(3qr-open 厨南墙东段)。
- **门槛线/台阶线(75 DROP)不是墙**: 不拆、G5 界面区避开; 合并房 measure 登记 erase 放行 flood, facts 保留为 opening/step 事实。
- **合并房 R9**: 源房 printed dims 整房对账已失效 — printed 清空, 原条目降级 derived 并打"[原<room>印刷尺寸]"标签(否则 R9 用 BATH 1025×1676 对 387sf 直接炸)。
- **V 形符号在 1974 型图 = 湿区门扇**(wet-lobby→WC/BATH 的门), 非 BTO 折叠门专利 — 随墙拆时一并划入拆除矩形。
- **收口位置尽量到门垛/交接点/柱边**(半岛墙梢 R13 会抓; 首例 3qr y867-902 stub)。
- **新墙贴黑RC 也要留 G3 领口**: 新墙双线贴黑墙脸会让 11×11 检测窗溢出报假柱 — 图面留 3px 领口
  (事实上砌到墙脸, 描述写明), flood 缝用短 seal 封(3qr-final 北围合墙 x165→x168)。
- **R19 砌墙轮扩展**: R19d Δ ∈ [-(built脚印+2), removed脚印+2](加墙面积会降); R19c 邻接
  built 矩形的房间同样豁免(4room-final 厨房被新墙吃掉一条)。
- **私享前室归属(用户复核定型)**: 走廊按"服务对象"切子段 — 只服务单一卧室门(含其套内卫)的
  端头段 = 该卧室前室, 归入卧室(共享虚拟界线切在最后一个共享门垛; 4room x545=WC2西门垛,
  主卧127→146sf); 服务≥2目的地的段才是 corridor; 门被砌掉后要**重判**(共享段可能变私享)。
  5room(走廊西端即主卧门)/3qr(foyer 服务两卧)无独享端头段, 维持原判。
- **克隆工作目录后清 stale assets**: 旧房间的 -2d/-3d/-crop/-dim 图会残留(如 bathroom-combined
  在 3qr-final), build_assets 不清理 — 手动删除再发布。
