#!/usr/bin/env python3
"""Loop 1 练习骨架：事实提取 loop（propose → verify → re-ask → degrade）。

你要写的只有 4 个 TODO，全部是流程控制，对应 agent/loops/loop_template.py 的槽位：
  TODO 1 = 槽位3 状态      TODO 2 = 槽位2 逐条裁决
  TODO 3 = 槽位2b 批检     TODO 4 = 槽位4+5 停机与降级

已经给你的零件（不用写）：
  propose()        生成器（stub 模式：从 demo/loop1_fixtures.json 读假提案，
                   会根据你回灌的 feedback 给出修正版 —— 模拟真 vision 的行为）
  verify.py        裁判函数库（referee / check_calibration / check_closure /
                   check_opening_on_wall / scale_from_calibrations）
  admit()          入库（把过审的提案写进 FactStore）
  degrade()        降级（把没救回来的条目标 review_required 入库）

跑法：  python3 agent/factlayer/extract_loop.py
写完的预期输出（对答案）：
  round 1: +6 admitted（4 标定 + top total + 南墙），4 rejected、原因回灌
  round 2: +3 admitted（depth / window-clear / door 的修正版），ceiling-drop 依然被拒
  round 3: +0（ceiling-drop 印刷污损，修不好）
  round 4: +0 → plateau（连续 2 轮零进展）与 MAX_ROUNDS 同时触发停机
  收尾:   dim.bedroom-2.ceiling-drop 降级 review_required
  最终:   store 里 11 条 fact（10 提案 + calibration.scale，其中 1 条 review_required），
          看 demo/inbox/factstore/loop1-sandbox-facts.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from store import FactStore                     # noqa: E402
from verify import (                            # noqa: E402
    Verdict, referee, check_calibration, check_closure,
    check_opening_on_wall, scale_from_calibrations, value_mm,
)

FIXTURES = json.loads((Path(__file__).parent.parent.parent / "demo/loop1_fixtures.json").read_text())
SANDBOX_PLAN = "demo/inbox/loop1-sandbox.jpg"   # 沙盒：只是命名用，不需要真图片
MAX_ROUNDS = 4
PLATEAU_LIMIT = 2


# ---------------------------------------------------------------- 已提供零件

def propose(open_ids: list[str], feedback: list[str], round_no: int) -> list[dict]:
    """生成器（stub）。第 1 轮给全量提案；之后只对 feedback 里点名的 id 给修正版
    （fixtures 里没有修正版的 = 模型救不回来的，永远给原样错误提案）。
    以后 WP1 换成真 vision 时，只改这个函数，loop 主体一行不动 —— 这就是
    生成器/裁判分离的意义。"""
    round1 = {p["id"]: p for p in FIXTURES["round1"]}
    corrections = FIXTURES["corrections"]
    if round_no == 1:
        return [round1[i] for i in open_ids if i in round1]
    named = {i for i in open_ids if any(i in fb for fb in feedback)}
    return [corrections.get(i, round1[i]) for i in open_ids if i in round1 and i in named]


def admit(store: FactStore, p: dict, scale: dict | None) -> None:
    """过审提案 → fact 入库。"""
    store.append("assert", {
        "id": p["id"], "layer": "fact", "kind": p["kind"],
        "p1": p["p1"], "p2": p["p2"],
        "value_mm": value_mm(p, scale) if scale else p.get("printed_mm"),
        "printed_mm": p.get("printed_mm"),
        "source": p["source"], "formula": p.get("formula"),
        "confidence": "high" if p.get("source") == "printed" else "medium",
        "host_wall_id": p.get("host_wall_id"),
        "review_required": False,
        "depends_on": [] if p["kind"] == "calibration" else ["calibration.scale"],
    }, actor="agent:extract-loop")


def degrade(store: FactStore, p: dict, reasons: list[str]) -> None:
    """救不回来的提案 → review_required 入库（绝不静默丢弃，绝不硬猜）。"""
    store.append("assert", {
        "id": p["id"], "layer": "fact", "kind": p["kind"],
        "p1": p.get("p1"), "p2": p.get("p2"),
        "value_mm": None, "printed_mm": p.get("printed_mm"),
        "source": p.get("source", "printed"), "formula": p.get("formula", "unresolved"),
        "confidence": "low", "review_required": True,
        "note": " | ".join(reasons[-3:]) or "extraction did not converge",
    }, actor="agent:extract-loop")


def latest_proposals(rounds: list[list[dict]]) -> dict:
    """每个 id 最后一次出现的提案（degrade 时要知道最终形态）。"""
    seen: dict[str, dict] = {}
    for proposals in rounds:
        for p in proposals:
            seen[p["id"]] = p
    return seen


# ---------------------------------------------------------------- 你的 4 个 TODO

def main() -> None:
    store = FactStore(SANDBOX_PLAN)
    if store.log_path.exists():
        store.log_path.unlink()                 # 沙盒每次重跑清零

    all_items = [p["id"] for p in FIXTURES["round1"]]

    # ============================================================
    # TODO 1 —— 状态（模板槽位3）
    # 初始化 loop 的全部状态变量：
    #   open_items      : 待办 id 列表（= all_items 的拷贝）
    #   admitted        : 已入库 {id: proposal}
    #   feedback        : 上一轮的结构化失败原因（字符串列表）
    #   reject_history  : {id: [原因, ...]}，degrade 时给人看
    #   round_no / no_progress_rounds / proposal_rounds（给 latest_proposals 用）
    # ============================================================
    raise NotImplementedError("TODO 1：先读 agent/factlayer/LOOP1_GUIDE.md，然后从这里开始写")

    # ============================================================
    # TODO 2 —— 主循环 + 逐条裁决（模板槽位1+2）
    # while 还有待办且没触发停机：
    #   proposals = propose(open_items, feedback, round_no)
    #   本轮顺序很重要：
    #   2a. 先处理 kind == "calibration" 的提案：全部收齐后跑
    #       check_calibration(标定列表)，通过才能 scale_from_calibrations()
    #       算出 scale —— 裁判没有比例尺就没法判尺寸（这是依赖顺序，
    #       loop 里经常有：某些事实是其他事实的裁判前提）。
    #       scale 算出来后别忘了把 calibration.scale 也 admit 进 store
    #       （可以直接 store.append 一条 kind=calibration 的 fact）。
    #   2b. 其余提案逐条 referee(p, scale)：
    #       ok → admit(store, p, scale)，从 open_items 移除
    #       不 ok → verdict.as_feedback() 追加进新一轮 feedback 和 reject_history
    #   2c. kind == "opening" 的提案多一道：check_opening_on_wall(p, 它的 host 墙)
    #       host 墙从 admitted 里找（host_wall_id）；墙还没入库 → 也算拒，
    #       feedback 写清"等待 host 墙"。
    # ============================================================

    # ============================================================
    # TODO 3 —— 批检（模板槽位2b）
    # 每轮逐条裁决完后，对 FIXTURES["closure_groups"] 里每组：
    #   组内全部 id 都已入库时，跑 check_closure(parts, total_mm, scale)
    #   （parts = admitted 里的提案；total_mm = value_mm(admitted[total_id], scale)）
    #   不过 → 整组打回：从 admitted 移除、塞回 open_items、原因进 feedback。
    # 本练习的 fixtures 闭合环是过的；写完后你可以故意改坏
    # demo/loop1_fixtures.json 里 calibration.x.b 的 printed_mm 看它被抓。
    # ============================================================

    # ============================================================
    # TODO 4 —— 停机 + 降级（模板槽位4+5）
    # 停机三保险：待办空 / round_no >= MAX_ROUNDS / 连续 PLATEAU_LIMIT 轮零进展。
    # 每轮结束 print 一行进展（round X: +N admitted, M open, K rejected）。
    # 循环结束后：open_items 里剩下的每个 id →
    #   degrade(store, latest_proposals(proposal_rounds)[id], reject_history[id])
    # 最后 store.write_snapshots() 并 print 汇总。
    # ============================================================


if __name__ == "__main__":
    main()
