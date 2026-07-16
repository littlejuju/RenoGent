#!/usr/bin/env python3
"""Deterministic referee library for the fact-extraction loop (WP0/WP1).

The extraction loop's generator (vision model) PROPOSES facts; these functions
are the only judge. Every check returns a Verdict — never raises on bad
proposals, so the loop can feed reasons back to the next round.

Single-proposal checks (call per proposal as it arrives):
  check_schema(proposal)
  check_scale_consistency(proposal, scale)

Batch checks (call once per round, after individual admits):
  check_closure(parts, total_mm)      — collinear parts must sum to the total
  check_opposite(a, b)                — opposite room edges must match
  check_opening_on_wall(opening, wall)

referee(proposal, scale) bundles the single-proposal checks.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

DIM_TOLERANCE_PCT = 1.5      # derived vs printed / closure / opposite edges
CALIBRATION_TOLERANCE_PCT = 1.0
ON_WALL_TOLERANCE_PX = 3.0


@dataclass
class Verdict:
    ok: bool
    code: str = "ok"
    reason: str = ""
    proposal_id: str = ""

    def as_feedback(self) -> str:
        return f"[{self.proposal_id or 'batch'}] {self.code}: {self.reason}"


def _pixel_len(p) -> float:
    return math.dist(p["p1"], p["p2"])


def _axis(p) -> str:
    dx = abs(p["p2"][0] - p["p1"][0])
    dy = abs(p["p2"][1] - p["p1"][1])
    return "x" if dx >= dy else "y"


def _mm_from_px(p, scale: dict) -> float:
    per_px = scale["x_mm_per_px"] if _axis(p) == "x" else scale["y_mm_per_px"]
    return _pixel_len(p) * per_px


def _pct_diff(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1e-9) * 100


# ---------- single-proposal checks ----------

def check_schema(p: dict) -> Verdict:
    pid = p.get("id", "?")
    for key in ("id", "kind", "p1", "p2", "source"):
        if key not in p:
            return Verdict(False, "schema-missing-field", f"proposal has no '{key}'", pid)
    if p["source"] == "printed" and not p.get("printed_mm"):
        return Verdict(False, "schema-printed-without-value",
                       "source=printed requires printed_mm (the number as printed on the plan)", pid)
    if p["source"] == "derived_from_scale" and not p.get("formula"):
        return Verdict(False, "schema-derived-without-formula",
                       "source=derived_from_scale requires a formula string", pid)
    if _pixel_len(p) < 2:
        return Verdict(False, "schema-degenerate-segment", "p1 and p2 are (nearly) the same point", pid)
    return Verdict(True, proposal_id=pid)


def check_scale_consistency(p: dict, scale: dict) -> Verdict:
    """A printed dimension must agree with what the calibrated scale measures
    between its own two pixel endpoints. Catches misread OCR digits AND
    misplaced endpoints — the two classic vision failure modes."""
    pid = p.get("id", "?")
    if p.get("source") != "printed":
        return Verdict(True, proposal_id=pid)
    measured = _mm_from_px(p, scale)
    printed = float(p["printed_mm"])
    diff = _pct_diff(measured, printed)
    if diff > DIM_TOLERANCE_PCT:
        return Verdict(False, "scale-mismatch",
                       f"printed {printed:.0f}mm but the segment measures {measured:.0f}mm "
                       f"at calibrated scale ({diff:.1f}% off) — re-read the printed number "
                       f"or re-place the endpoints", pid)
    return Verdict(True, proposal_id=pid)


def referee(p: dict, scale: dict) -> Verdict:
    for check in (check_schema, lambda q: check_scale_consistency(q, scale)):
        v = check(p)
        if not v.ok:
            return v
    return Verdict(True, proposal_id=p.get("id", "?"))


# ---------- batch checks ----------

def value_mm(p: dict, scale: dict) -> float:
    """The value a proposal contributes: printed number if trusted, else derived."""
    if p.get("source") == "printed":
        return float(p["printed_mm"])
    return _mm_from_px(p, scale)


def check_closure(parts: list[dict], total_mm: float, scale: dict, name: str = "closure") -> Verdict:
    """Consecutive collinear segments must sum to the printed total.
    e.g. service block 4648 + study 2895 + bedroom1 2896 = top width 10439."""
    total = sum(value_mm(p, scale) for p in parts)
    diff = _pct_diff(total, total_mm)
    ids = [p.get("id", "?") for p in parts]
    if diff > DIM_TOLERANCE_PCT:
        return Verdict(False, "closure-violation",
                       f"{' + '.join(ids)} = {total:.0f}mm but the printed total is "
                       f"{total_mm:.0f}mm ({diff:.1f}% off) — one of these segments is wrong", name)
    return Verdict(True, proposal_id=name)


def check_opposite(a: dict, b: dict, scale: dict) -> Verdict:
    """Opposite edges of a rectangular room must be equal (HDB rooms are
    orthogonal; a mismatch means one endpoint slipped onto the wrong wall)."""
    va, vb = value_mm(a, scale), value_mm(b, scale)
    diff = _pct_diff(va, vb)
    if diff > DIM_TOLERANCE_PCT:
        return Verdict(False, "opposite-edge-mismatch",
                       f"{a.get('id')} = {va:.0f}mm vs {b.get('id')} = {vb:.0f}mm ({diff:.1f}% off)",
                       f"{a.get('id')}~{b.get('id')}")
    return Verdict(True, proposal_id=f"{a.get('id')}~{b.get('id')}")


def _point_on_segment(pt, a, b, tol=ON_WALL_TOLERANCE_PX) -> bool:
    seg = math.dist(a, b)
    if seg == 0:
        return math.dist(pt, a) <= tol
    cross = abs((pt[0] - a[0]) * (b[1] - a[1]) - (pt[1] - a[1]) * (b[0] - a[0])) / seg
    if cross > tol:
        return False
    dot = (pt[0] - a[0]) * (b[0] - a[0]) + (pt[1] - a[1]) * (b[1] - a[1])
    return -tol * seg <= dot <= seg * seg + tol * seg


def check_opening_on_wall(opening: dict, wall: dict) -> Verdict:
    """A door/window opening must lie ON its host wall segment."""
    pid = opening.get("id", "?")
    for name, pt in (("p1", opening["p1"]), ("p2", opening["p2"])):
        if not _point_on_segment(pt, wall["p1"], wall["p2"]):
            return Verdict(False, "opening-off-wall",
                           f"{name} {pt} does not lie on wall {wall.get('id')} "
                           f"({wall['p1']}→{wall['p2']}) — wrong wall or slipped endpoint", pid)
    return Verdict(True, proposal_id=pid)


# ---------- calibration ----------

def check_calibration(calibrations: list[dict]) -> Verdict:
    """≥2 printed references per axis, residuals within tolerance of each other."""
    by_axis: dict[str, list[float]] = {"x": [], "y": []}
    for c in calibrations:
        axis = c.get("axis") or _axis(c)
        by_axis.setdefault(axis, []).append(float(c["printed_mm"]) / _pixel_len(c))
    for axis, vals in by_axis.items():
        if len(vals) < 2:
            return Verdict(False, "calibration-underdetermined",
                           f"axis {axis} has {len(vals)} printed reference(s); need ≥2 to cross-check", "calibration")
        spread = _pct_diff(max(vals), min(vals))
        if spread > CALIBRATION_TOLERANCE_PCT:
            return Verdict(False, "calibration-inconsistent",
                           f"axis {axis} mm/px references disagree by {spread:.2f}% — "
                           f"one reference is misread or the image is distorted", "calibration")
    return Verdict(True, proposal_id="calibration")


def scale_from_calibrations(calibrations: list[dict]) -> dict:
    by_axis: dict[str, list[float]] = {"x": [], "y": []}
    for c in calibrations:
        axis = c.get("axis") or _axis(c)
        by_axis.setdefault(axis, []).append(float(c["printed_mm"]) / _pixel_len(c))
    return {
        "x_mm_per_px": sum(by_axis["x"]) / len(by_axis["x"]),
        "y_mm_per_px": sum(by_axis["y"]) / len(by_axis["y"]),
    }
