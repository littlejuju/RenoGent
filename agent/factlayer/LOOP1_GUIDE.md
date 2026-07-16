# Loop 1 练习指南 —— 你要写什么、为什么这么写

## 先回答你的问题：「是需要我写几个 JSON 吗？」

不是。JSON 是 loop 的**输入输出**（弹药和战果），loop 本身是 `extract_loop.py` 里
`main()` 函数中的一个 **while 循环**。你要写的是流程控制代码（Python），
大约 60–80 行。所有数据格式、裁判函数、生成器我都已经写好，你只负责把它们串起来。

## 你的可复用模板

`agent/loops/loop_template.py` —— 以后任何项目要搭 loop，先把它的**五个槽位**想清楚：

| 槽位 | 问自己 | 本练习里对应 |
|---|---|---|
| 1 生成器 | 谁出提案？（只有提案权） | `propose()`（已提供，stub） |
| 2 裁判 | 谁裁决？必须独立于生成器，优先确定性代码 | `verify.py` 全家（已提供） |
| 3 状态 | 循环在推进什么？每轮落盘什么？ | **TODO 1（你写）** |
| 4 停机 | 完成 / 预算 / plateau 三重保险 | **TODO 4 前半（你写）** |
| 5 降级 | 没清零的待办去哪？绝不静默丢弃 | **TODO 4 后半（你写）** |

TODO 2（逐条裁决）和 TODO 3（批检）是槽位 2 的两种用法：
单条提案立刻能判的（schema、比例尺一致性）逐条判；
要凑齐多条才能判的（闭合环求和）每轮末批判，抓到了要把**已入库的同伙打回待办**。

## 动手步骤

1. 读一遍 `agent/loops/loop_template.py`（15 分钟，模板本身能跑，但你不用跑它）
2. 打开 `agent/factlayer/extract_loop.py`，按 TODO 1→2→3→4 顺序填空
3. 每写完一段就跑 `python3 agent/factlayer/extract_loop.py` 看报错，不用等全写完
4. 对答案：文件头部注释里有预期输出（round 1: +6 … 最终 11 条 fact）
5. 跑通后做扩展练习（见下）

## 卡住时的提示（按 TODO）

- **TODO 1**：就是七八个变量赋值。关键认知：状态**显式**列出来（而不是散落在
  循环体里临时冒出），loop 才可能中断续跑、才可能事后取证。
- **TODO 2**：顺序陷阱——裁判判尺寸需要比例尺，比例尺来自标定提案。所以每轮先
  处理 `kind=="calibration"`（用 `check_calibration` 批检 → `scale_from_calibrations`），
  再判其余。`scale` 算出来后跨轮保留（round 2 不会再有标定提案）。
  opening 多一道 `check_opening_on_wall`，host 墙从已入库里查。
- **TODO 3**：`FIXTURES["closure_groups"]`，组内成员全入库了才判。判失败 →
  整组从 admitted 弹回 open_items。想看它工作：故意把 fixtures 里
  `calibration.x.b` 的 printed_mm 改成 2500 再跑。
- **TODO 4**：`while open_items and round_no < MAX_ROUNDS and no_progress < PLATEAU_LIMIT`
  就是三重保险的直译。降级用已提供的 `degrade()`。

## 最重要的三个概念（这个练习真正教的东西）

1. **生成器和裁判分离**：`propose()` 换成真 vision 模型时，loop 主体一行不改。
   裁判是确定性几何代码 → 模型幻觉过不了关，这就是「vision 只提案，几何做裁判」。
2. **反馈要结构化**：被拒提案的 `verdict.as_feedback()` 里有 id + 差多少 + 往哪查。
   下一轮生成器靠它给修正版 —— re-ask 不是「重试一次」，是「带着具体矛盾重问」。
3. **降级出口**：ceiling-drop 永远修不好（印刷污损），loop 不硬猜也不死循环，
   降级 review_required 交给人。**loop 的出口设计比循环体重要。**

## 扩展练习（跑通后）

1. 弄坏闭合环（见 TODO 3 提示），观察「已入库被打回」的机制
2. 给 `propose()` 加一个 `--real` 模式：用 `claude -p`（参考 plan_briefs.js 的
   调用方式）对真户型图出提案 —— 这就是 WP1 的正式版本，你的 loop 直接升级为生产代码
3. 读 `agent/factlayer/render_all.js` 的 151–186 行（Loop 2），
   对着模板五槽位标注它的每个部件：它多了「分数函数 + plateau 早退 +
   learned constraints 烧进新 base」三个进阶件

## 验证你的成果

跑通后执行：
```
python3 agent/factlayer/store.py snapshot demo/inbox/loop1-sandbox.jpg
```
应显示 11 条 fact、1 条 review_required（dim.bedroom-2.ceiling-drop）。
