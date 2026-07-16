#!/usr/bin/env python3
"""WP0 migration: fold the existing per-plan artifacts into the fact store.

Sources:
  <plan>-dimension-decomposition-v1-manifest.json  → L1 facts (calibration, dims,
                                                     room polygons)
  <plan without -cropped>-briefs.json              → L2 inferences (windows/doors/
                                                     function/fixtures as vision
                                                     conjectures) + L3 briefs
                                                     (camera, design notes)
  existing whitebox PNGs                           → registered artifacts (so a
                                                     later fact override marks
                                                     them stale)

Usage: python3 agent/factlayer/migrate_demo.py demo/inbox/plan-1783836724077-cropped.jpg [--force]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from store import FactStore  # noqa: E402

DIMENSION_VARIANT = "dimension-decomposition-v1"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def main() -> None:
    plan = Path(sys.argv[1])
    force = "--force" in sys.argv
    store = FactStore(plan)
    if store.log_path.exists():
        if not force:
            sys.exit(f"log already exists: {store.log_path} (use --force to rebuild)")
        store.log_path.unlink()

    manifest_path = plan.parent / f"{plan.stem}-{DIMENSION_VARIANT}-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    briefs_path = plan.parent / f"{plan.stem.replace('-cropped', '')}-briefs.json"
    briefs = json.loads(briefs_path.read_text()) if briefs_path.exists() else {"rooms": []}

    actor = "migrate:wp0"
    calibration_ids = []
    for c in manifest["calibration_segments"]:
        cid = f"calibration.{c['axis']}.{slug(c['name'])}"
        calibration_ids.append(cid)
        store.append("assert", {
            "id": cid, "layer": "fact", "kind": "calibration",
            "axis": c["axis"], "p1": c["p1"], "p2": c["p2"],
            "printed_mm": c["printed_mm"], "value_mm": c["printed_mm"],
            "source": "printed", "confidence": c.get("confidence", "high"),
            "source_label": c.get("source_label", ""),
            "review_required": False,
        }, actor)
    store.append("assert", {
        "id": "calibration.scale", "layer": "fact", "kind": "calibration",
        "value": manifest["scale"], "source": "derived_from_scale",
        "formula": "mean mm/px of printed axis references",
        "confidence": "high", "depends_on": calibration_ids,
        "review_required": False,
    }, actor)

    dim_ids = {}
    for room in manifest.get("rooms", []):
        rslug = slug(room["room"])
        dim_ids[room["room"]] = []
        if room.get("interior_polygon"):
            store.append("assert", {
                "id": f"room_polygon.{rslug}", "layer": "fact", "kind": "room_polygon",
                "polygon_px": room["interior_polygon"], "source": "derived_from_scale",
                "formula": "traced interior envelope on plan",
                "confidence": "medium", "depends_on": ["calibration.scale"],
                "review_required": room.get("identity_status") != "verified",
                "note": room.get("identity_note", ""),
            }, actor)
        for seg in room.get("segments", []):
            fid = f"dim.{rslug}.{slug(seg['name'])}"
            dim_ids[room["room"]].append(fid)
            printed = "printed" in (seg.get("source") or "")
            store.append("assert", {
                "id": fid, "layer": "fact", "kind": "dim",
                "room": room["room"], "name": seg["name"],
                "p1": seg["p1"], "p2": seg["p2"],
                "value_mm": seg.get("expected_mm") or seg.get("computed_mm"),
                "printed_mm": seg.get("expected_mm") if printed else None,
                "source": "printed" if printed else "derived_from_scale",
                "formula": seg.get("formula") or "px_len * mm_per_px",
                "confidence": seg.get("confidence", "medium"),
                "measurement_kind": seg.get("measurement_kind", "unknown"),
                "feeds_whitebox": seg.get("effective_feeds_whitebox", False),
                "review_required": bool(seg.get("review_required")),
                "note": seg.get("note", ""),
                "depends_on": ["calibration.scale"],
            }, actor)

    for room in briefs.get("rooms", []):
        rslug = slug(room["name"])
        for kind, text in (("windows", room.get("windows")), ("doors", room.get("doors")),
                           ("fixtures", room.get("fixtures")), ("room_function", room.get("actual_function"))):
            if not text:
                continue
            store.append("assert", {
                "id": f"inference.{rslug}.{kind}", "layer": "inference", "kind": kind,
                "claim": text, "basis": "vision_brief:plan_briefs.js",
                "confidence": "medium", "status": "proposed",
                "depends_on": [f"room_polygon.{rslug}"] if f"room_polygon.{rslug}" in store.entries() else [],
            }, actor)
        store.append("assert", {
            "id": f"brief.{rslug}.camera", "layer": "brief", "kind": "camera",
            "camera": room.get("camera"), "camera_px": room.get("camera_px"),
            "look_at_px": room.get("look_at_px"),
            "expected_components": room.get("expected_components"),
            "visible_from_camera": room.get("visible_from_camera"),
        }, actor)
        if room.get("design_notes"):
            store.append("assert", {
                "id": f"brief.{rslug}.design-notes", "layer": "brief", "kind": "design_notes",
                "notes": room["design_notes"],
            }, actor)

    canon = lambda s: slug(s).replace("-", "")
    for png in sorted(plan.parent.glob("*whitebox-traced-axon.png")):
        room_slug = png.name.replace("-whitebox-traced-axon.png", "")
        inputs = next((ids for name, ids in dim_ids.items()
                       if canon(name).startswith(canon(room_slug)) or canon(room_slug) in canon(name)), [])
        store.record_artifact(f"whitebox.{room_slug}", str(png),
                              (inputs or [i for ids in dim_ids.values() for i in ids]) + ["calibration.scale"],
                              actor)

    store.write_snapshots()
    entries, artifacts, version = store.replay()
    print(f"migrated → {store.log_path}")
    print(f"version {version}: {len(entries)} entries, {len(artifacts)} artifacts")


if __name__ == "__main__":
    main()
