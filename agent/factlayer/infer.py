#!/usr/bin/env python3
"""HDB-norm inference engine (WP2 of plans/designer-v2.md).

Applies agent/factlayer/hdb_rules.json to the L1 facts in a plan's fact store
and emits L2 inferences (status=proposed). Design contract:

- Rules are data (thresholds/claims/confidence in hdb_rules.json); the matcher
  per rule `kind` is code here. New threshold = edit JSON, no code change.
- Every inference carries depends_on → overriding an L1 fact marks dependent
  inferences stale through the store's dependency graph (WP0).
- User verdicts are never clobbered: entries whose status is user_confirmed or
  user_overridden are skipped on re-runs. Unchanged proposed claims are also
  skipped to keep the event log quiet.
- Rules whose required fact kinds are missing are reported as skipped, not
  silently dropped — WP1 will fill wall facts and unlock them.

Usage: python3 agent/factlayer/infer.py <plan> [--dry-run]
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from store import FactStore  # noqa: E402

RULES_PATH = Path(__file__).parent / "hdb_rules.json"
ACTOR = "agent:infer-hdb"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


@dataclass
class RoomCtx:
    name: str
    slug: str
    dims: list[dict] = field(default_factory=list)          # dim fact entries (with id)
    polygon_id: str | None = None
    brief_inference_ids: dict[str, str] = field(default_factory=dict)  # kind → entry id

    @property
    def enclosed_sides(self) -> int:
        return sum(1 for d in self.dims if d.get("measurement_kind") == "interior_clear")

    @property
    def window_evidence(self) -> list[str]:
        ids = [d["id"] for d in self.dims
               if d.get("measurement_kind") == "window_opening" or "window" in (d.get("name") or "")]
        if "windows" in self.brief_inference_ids:
            ids.append(self.brief_inference_ids["windows"])
        return ids

    @property
    def max_span(self) -> tuple[float, str, str] | None:
        spans = [(d.get("value_mm") or 0, d.get("name", ""), d["id"]) for d in self.dims
                 if d.get("value_mm")]
        return max(spans) if spans else None


def build_rooms(entries: dict) -> dict[str, RoomCtx]:
    rooms: dict[str, RoomCtx] = {}

    def room_for(name: str) -> RoomCtx:
        s = slug(name)
        if s not in rooms:
            rooms[s] = RoomCtx(name=name, slug=s)
        return rooms[s]

    for eid, e in entries.items():
        if e.get("layer") == "fact" and e.get("kind") == "dim" and e.get("room"):
            room_for(e["room"]).dims.append({**e, "id": eid})
        elif e.get("layer") == "fact" and e.get("kind") == "room_polygon":
            room_for(eid.removeprefix("room_polygon.").replace("-", " ")).polygon_id = eid
        elif e.get("layer") in ("inference", "brief"):
            m = re.match(r"(?:inference|brief)\.([a-z0-9-]+)\.([a-z_-]+)$", eid)
            if m and e.get("layer") == "inference":
                room_for(m.group(1).replace("-", " ")).brief_inference_ids.setdefault(m.group(2), eid)
            elif m:
                room_for(m.group(1).replace("-", " "))  # ensure brief-only rooms exist
    return rooms


def emit(store: FactStore, existing: dict, out: list, *, entry_id: str, rule: dict,
         claim: str, depends_on: list[str], dry_run: bool) -> None:
    prior = existing.get(entry_id)
    if prior and prior.get("status") in ("user_confirmed", "user_overridden"):
        out.append(("respected-user-verdict", entry_id))
        return
    if prior and prior.get("claim") == claim and set(prior.get("depends_on", [])) == set(depends_on):
        out.append(("unchanged", entry_id))
        return
    entry = {
        "id": entry_id, "layer": "inference", "kind": rule["kind"],
        "claim": claim, "basis": rule["basis"],
        "rule_id": rule["id"], "confidence": rule["confidence"],
        "status": "proposed",
        "needs_user_confirmation": bool(rule.get("needs_user_confirmation")),
        "depends_on": sorted(set(depends_on)),
    }
    if not dry_run:
        store.append("assert", entry, ACTOR)
    out.append(("emitted", entry_id))


def apply_rules(store: FactStore, dry_run: bool = False) -> list[tuple[str, str]]:
    entries = store.entries()
    rooms = build_rooms(entries)
    rules = json.loads(RULES_PATH.read_text())["rules"]
    fact_kinds = {e.get("kind") for e in entries.values() if e.get("layer") == "fact"}
    out: list[tuple[str, str]] = []

    for rule in rules:
        missing = [k for k in rule.get("requires_fact_kinds", []) if k not in fact_kinds]
        if missing:
            out.append(("skipped-missing-facts", f"{rule['id']} (needs {','.join(missing)} facts — unlocked by WP1)"))
            continue
        p = rule.get("params", {})

        if rule["scope"] == "unit":
            claim = rule["claim_template"].format(walls="?", **{k: v for k, v in p.items()})
            emit(store, entries, out, entry_id=f"inference.unit.{rule['id']}", rule=rule,
                 claim=claim, depends_on=[], dry_run=dry_run)
            continue

        for room in rooms.values():
            rid = f"inference.{room.slug}.{rule['id']}"
            if rule["kind"] == "window_type":
                evidence = room.window_evidence
                if not evidence:
                    continue
                claim = rule["claim_template"].format(room=room.name, sill_m=p["sill_mm"] / 1000)
                emit(store, entries, out, entry_id=rid, rule=rule, claim=claim,
                     depends_on=evidence, dry_run=dry_run)

            elif rule["id"] == "enclosed-room-by-homeowner":
                if not any(h in room.slug for h in p["interior_room_name_hints"]):
                    continue
                if room.enclosed_sides < p["min_enclosed_sides"]:
                    continue
                claim = rule["claim_template"].format(room=room.name, sides=room.enclosed_sides)
                deps = [d["id"] for d in room.dims if d.get("measurement_kind") == "interior_clear"]
                if room.polygon_id:
                    deps.append(room.polygon_id)
                emit(store, entries, out, entry_id=rid, rule=rule, claim=claim,
                     depends_on=deps, dry_run=dry_run)

            elif rule["id"] == "service-passage-vs-balcony":
                narrow = any(0 < (d.get("value_mm") or 0) < p["max_passage_width_mm"] for d in room.dims)
                named = any(h in room.slug for h in p["service_name_hints"])
                if not (named or (narrow and "balcony" in room.slug)):
                    continue
                claim = rule["claim_template"].format(room=room.name)
                emit(store, entries, out, entry_id=rid, rule=rule, claim=claim,
                     depends_on=[d["id"] for d in room.dims], dry_run=dry_run)

            elif rule["kind"] == "beam" and rule["scope"] == "room":
                span = room.max_span
                if not span or span[0] <= p["span_threshold_mm"]:
                    continue
                claim = rule["claim_template"].format(room=room.name, span_mm=round(span[0]),
                                                      span_name=span[1])
                emit(store, entries, out, entry_id=rid, rule=rule, claim=claim,
                     depends_on=[span[2]], dry_run=dry_run)

            elif rule["kind"] == "pipes":
                if not any(h in room.slug or h in room.name.lower() for h in p["wet_name_hints"]):
                    continue
                claim = rule["claim_template"].format(room=room.name)
                emit(store, entries, out, entry_id=rid, rule=rule, claim=claim,
                     depends_on=[d["id"] for d in room.dims], dry_run=dry_run)

    if not dry_run:
        store.write_snapshots()
    return out


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    store = FactStore(sys.argv[1])
    results = apply_rules(store, dry_run="--dry-run" in sys.argv)
    by_status: dict[str, list[str]] = {}
    for status, what in results:
        by_status.setdefault(status, []).append(what)
    for status, items in by_status.items():
        print(f"{status} ({len(items)}):")
        for w in items:
            print(f"  {w}")


if __name__ == "__main__":
    main()
