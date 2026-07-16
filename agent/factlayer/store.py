#!/usr/bin/env python3
"""Event-sourced fact store (WP0 of plans/designer-v2.md).

One append-only log per floor plan. The current fact/inference snapshot is a
pure replay of the log; every downstream artifact records the log version it
was built from, so any later change to its inputs makes it stale.

Layers (entry["layer"]):
  fact       L1 metric facts   (calibration, dim, wall, door, window, opening,
                                room_polygon, adjacency)
  inference  L2 HDB-norm conjectures (status: proposed | user_confirmed |
                                user_overridden — latest event wins)
  brief      L3 homeowner brief / vetoes / camera specs

Events (one JSON per line):
  {"seq": 3, "ts": "...", "actor": "user", "action": "assert|override|confirm|
   retract|artifact", "entry": {...}}

CLI:
  python3 store.py snapshot <plan>            # rebuild + print summary
  python3 store.py override <plan> <id> k=v…  # user override (marks dependents)
  python3 store.py confirm  <plan> <id>       # user confirms an inference
  python3 store.py stale    <plan>            # list stale artifacts + entries
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FACT_SOURCES = {"printed", "derived_from_scale", "user_provided"}
INFERENCE_STATUS = {"proposed", "user_confirmed", "user_overridden"}
LAYERS = {"fact", "inference", "brief"}


class SchemaError(ValueError):
    pass


def validate_entry(entry: dict) -> None:
    for key in ("id", "layer", "kind"):
        if not entry.get(key):
            raise SchemaError(f"entry missing required field '{key}': {entry}")
    layer = entry["layer"]
    if layer not in LAYERS:
        raise SchemaError(f"{entry['id']}: unknown layer '{layer}'")
    if layer == "fact":
        source = entry.get("source")
        if source not in FACT_SOURCES:
            raise SchemaError(f"{entry['id']}: fact source must be one of {sorted(FACT_SOURCES)}, got '{source}'")
        if source == "derived_from_scale" and not entry.get("formula"):
            raise SchemaError(f"{entry['id']}: derived_from_scale facts must carry a 'formula'")
        if not entry.get("confidence"):
            raise SchemaError(f"{entry['id']}: fact missing 'confidence'")
    if layer == "inference":
        if not entry.get("claim") or not entry.get("basis"):
            raise SchemaError(f"{entry['id']}: inference needs 'claim' and 'basis'")
        if entry.get("status", "proposed") not in INFERENCE_STATUS:
            raise SchemaError(f"{entry['id']}: bad inference status '{entry.get('status')}'")


class FactStore:
    def __init__(self, plan_path: str | Path):
        self.plan = Path(plan_path)
        self.dir = self.plan.parent / "factstore"
        self.dir.mkdir(exist_ok=True)
        self.log_path = self.dir / f"{self.plan.stem}.log.jsonl"

    # ---------- log primitives ----------

    def events(self) -> list[dict]:
        if not self.log_path.exists():
            return []
        return [json.loads(line) for line in self.log_path.read_text().splitlines() if line.strip()]

    def append(self, action: str, entry: dict, actor: str) -> dict:
        if action in ("assert", "override"):
            base = self.entries().get(entry.get("id"), {}) if action == "override" else {}
            if action == "override" and not base:
                raise SchemaError(f"override target '{entry.get('id')}' does not exist")
            validate_entry({**base, **entry})
        event = {
            "seq": len(self.events()) + 1,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "actor": actor,
            "action": action,
            "entry": entry,
        }
        with self.log_path.open("a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.write_snapshots()
        return event

    # ---------- replay ----------

    def replay(self) -> tuple[dict, list[dict], int]:
        """Returns (entries_by_id, artifacts, version)."""
        entries: dict[str, dict] = {}
        artifacts: list[dict] = []
        version = 0
        for ev in self.events():
            version = ev["seq"]
            e = ev["entry"]
            eid = e.get("id")
            if ev["action"] == "assert":
                entries[eid] = {**e, "_seq": ev["seq"]}
            elif ev["action"] == "override":
                merged = {**entries[eid], **e, "_seq": ev["seq"]}
                if merged.get("layer") == "inference":
                    merged["status"] = "user_overridden"
                merged.setdefault("history", [])
                entries[eid] = merged
            elif ev["action"] == "confirm":
                entries[eid] = {**entries[eid], "status": "user_confirmed", "_seq": ev["seq"]}
            elif ev["action"] == "retract":
                entries.pop(eid, None)
            elif ev["action"] == "artifact":
                artifacts.append({**e, "_seq": ev["seq"]})
        return entries, artifacts, version

    def entries(self) -> dict:
        return self.replay()[0]

    def version(self) -> int:
        return self.replay()[2]

    # ---------- dependency / stale propagation ----------

    def dependents(self, changed_ids: set[str]) -> set[str]:
        """Transitive closure of entries whose depends_on touches changed_ids."""
        entries = self.entries()
        affected = set(changed_ids)
        grew = True
        while grew:
            grew = False
            for eid, e in entries.items():
                if eid in affected:
                    continue
                if set(e.get("depends_on", [])) & affected:
                    affected.add(eid)
                    grew = True
        return affected - set(changed_ids)

    def changed_since(self, version: int) -> set[str]:
        return {ev["entry"].get("id") for ev in self.events()
                if ev["seq"] > version and ev["action"] in ("assert", "override", "confirm", "retract")}

    def record_artifact(self, name: str, path: str, input_ids: list[str], actor: str = "system") -> dict:
        return self.append("artifact", {
            "id": f"artifact.{name}",
            "layer": "artifact", "kind": "artifact",  # not validated as fact
            "name": name, "path": path, "input_ids": input_ids,
            "based_on_version": self.version(),
        }, actor)

    def stale_artifacts(self) -> list[dict]:
        entries, artifacts, _ = self.replay()
        out = []
        for a in artifacts:
            direct = self.changed_since(a["based_on_version"])
            if not direct:
                continue
            hit = (set(a["input_ids"]) & direct) | (set(a["input_ids"]) & self.dependents(direct))
            if hit:
                out.append({**a, "stale_because": sorted(hit)})
        return out

    # ---------- snapshots ----------

    def write_snapshots(self) -> None:
        entries, _, version = self.replay()
        by_layer: dict[str, dict] = {"fact": {}, "inference": {}, "brief": {}}
        for eid, e in entries.items():
            layer = e.get("layer")
            if layer in by_layer:
                by_layer[layer][eid] = {k: v for k, v in e.items() if not k.startswith("_")}
        header = {"plan": str(self.plan), "version": version}
        for layer, fname in (("fact", "facts.json"), ("inference", "inferences.json"), ("brief", "brief.json")):
            (self.dir / f"{self.plan.stem}-{fname}").write_text(
                json.dumps({**header, "entries": by_layer[layer]}, indent=1, ensure_ascii=False))


def _parse_kv(pairs: list[str]) -> dict:
    out = {}
    for p in pairs:
        k, _, v = p.partition("=")
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cmd, plan = sys.argv[1], sys.argv[2]
    store = FactStore(plan)
    if cmd == "snapshot":
        entries, artifacts, version = store.replay()
        store.write_snapshots()
        counts: dict[str, int] = {}
        for e in entries.values():
            counts[e.get("layer")] = counts.get(e.get("layer"), 0) + 1
        review = [i for i, e in entries.items() if e.get("review_required")]
        print(f"version {version} · {counts} · artifacts {len(artifacts)} · review_required {len(review)}")
        for eid in review:
            print(f"  review: {eid}")
    elif cmd == "override":
        eid, kv = sys.argv[3], _parse_kv(sys.argv[4:])
        ev = store.append("override", {"id": eid, **kv}, actor="user")
        affected = store.dependents({eid})
        print(f"seq {ev['seq']} override {eid}")
        print(f"dependents now stale: {sorted(affected) or 'none'}")
        for a in store.stale_artifacts():
            print(f"stale artifact: {a['name']} ({a['path']}) because {a['stale_because']}")
    elif cmd == "confirm":
        ev = store.append("confirm", {"id": sys.argv[3]}, actor="user")
        print(f"seq {ev['seq']} confirmed {sys.argv[3]}")
    elif cmd == "stale":
        stale = store.stale_artifacts()
        if not stale:
            print("no stale artifacts")
        for a in stale:
            print(f"{a['name']} ({a['path']}) stale because {a['stale_because']}")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
