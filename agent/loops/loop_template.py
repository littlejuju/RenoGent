#!/usr/bin/env python3
"""通用 agentic loop 模板 —— 五个槽位，任何 propose→verify→repair 循环都是它的实例。

┌─────────────────────────────────────────────────────────────┐
│  while 还有待办 and 预算没烧完:                                │
│      提案 = GENERATOR(待办, 上轮反馈)      ← 槽位1 生成器      │
│      for p in 提案:                                          │
│          裁决 = REFEREE(p)                ← 槽位2 裁判        │
│          过 → 入库(STATE)；不过 → 结构化反馈                   │
│      批检 = BATCH_REFEREE(已入库)          ← 槽位2b 全局一致性 │
│      冲突的已入库条目 → 打回待办                               │
│      if 本轮零进展: 死胡同计数 += 1        ← 槽位4 停机策略    │
│  收尾: 剩余待办全部降级/上报               ← 槽位5 降级出口    │
└─────────────────────────────────────────────────────────────┘

五个槽位（写任何 loop 前先把这五样想清楚，再动键盘）：

1. GENERATOR 生成器 —— 谁出提案（LLM/vision/规则）。只有提案权，没有裁决权。
2. REFEREE   裁判   —— 独立于生成器的校验。优先确定性代码（几何/求和/schema），
                       其次才是另一个模型。绝不让生成器给自己打分。
                       裁决必须带【机器可读的失败原因】，因为它就是下一轮的 prompt 原料。
3. STATE     状态   —— 循环在推进什么：待办集合、已入库集合、反馈列表、轮数、花费。
                       每轮结束状态必须落盘（audit trail），loop 挂了能续跑、事后能取证。
4. STOP      停机   —— 三重保险，一个都不能少：
                       a. 完成（待办空了）
                       b. 预算上限（MAX_ROUNDS / MAX_COST）
                       c. plateau（连续 N 轮零进展 = 死胡同，继续烧钱没有意义）
5. DEGRADE   降级   —— loop 结束时待办没清零怎么办：降级标记（review_required）、
                       上报人审（escalation）、或换策略重开（fresh base）。
                       绝不静默丢弃，绝不硬猜。

────────────────────────────────────────────────────────────────
最小可运行骨架（复制改造）：
"""
from dataclasses import dataclass, field


@dataclass
class LoopState:                        # 槽位3：状态显式化，不藏在局部变量里
    open_items: list                    # 待办
    admitted: dict = field(default_factory=dict)   # 已入库 {id: item}
    feedback: list = field(default_factory=list)   # 上一轮的结构化失败原因
    round_no: int = 0
    no_progress_rounds: int = 0
    trail: list = field(default_factory=list)      # 每轮快照（audit trail）


def run_loop(state, generator, referee, batch_referee, admit, degrade,
             max_rounds=3, plateau_limit=2, log=print):
    while state.open_items:
        # ---- 槽位4：停机策略（预算 + plateau）----
        if state.round_no >= max_rounds:
            log(f"stop: hit MAX_ROUNDS={max_rounds}")
            break
        if state.no_progress_rounds >= plateau_limit:
            log(f"stop: {plateau_limit} rounds with zero progress (plateau)")
            break
        state.round_no += 1
        progressed = 0

        # ---- 槽位1：生成器只出提案 ----
        proposals = generator(state.open_items, state.feedback, state.round_no)
        state.feedback = []

        # ---- 槽位2：逐条独立裁决 ----
        for p in proposals:
            verdict = referee(p, state)
            if verdict.ok:
                admit(p, state)
                state.open_items = [i for i in state.open_items if i != p["id"]]
                progressed += 1
            else:
                # 失败原因是下一轮 prompt 的原料 —— 要具体（哪条、差多少、往哪查）
                state.feedback.append(verdict.as_feedback())

        # ---- 槽位2b：全局一致性批检，冲突条目打回待办 ----
        for verdict, guilty_ids in batch_referee(state):
            if not verdict.ok:
                state.feedback.append(verdict.as_feedback())
                for gid in guilty_ids:
                    state.admitted.pop(gid, None)
                    if gid not in state.open_items:
                        state.open_items.append(gid)
                        progressed -= 1

        state.no_progress_rounds = 0 if progressed > 0 else state.no_progress_rounds + 1
        state.trail.append({"round": state.round_no, "admitted": len(state.admitted),
                            "open": len(state.open_items), "feedback": list(state.feedback)})
        log(f"round {state.round_no}: +{progressed} admitted, "
            f"{len(state.open_items)} open, {len(state.feedback)} rejections")

    # ---- 槽位5：降级出口，绝不静默丢弃 ----
    if state.open_items:
        degrade(state.open_items, state)
    return state
