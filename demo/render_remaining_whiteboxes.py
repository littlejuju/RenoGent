#!/usr/bin/env python3
"""Deterministic whitebox renders for the remaining RenoGent unit rooms.

These are structure approval references, not styled interior renders. They
avoid image-generation for the geometry pass: every room is drawn from the
cached fact-layer briefs and the original HDB plan proportions.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw


OUT_DIR = Path("demo/inbox")
W, H = 1400, 1000
WALL_H = 2600
COMMON_SCALE = 0.135
DIM_TOLERANCE = 0.015
AUDIT_VARIANT = "edge-audit-v4"
DIMENSION_VARIANT = "dimension-decomposition-v1"
PLAN_IMAGE = OUT_DIR / "plan-1783836724077-cropped.jpg"
DIMENSION_MANIFEST = OUT_DIR / f"{PLAN_IMAGE.stem}-{DIMENSION_VARIANT}-manifest.json"

Point2 = tuple[float, float]
Point3 = tuple[float, float, float]
Color = tuple[int, int, int, int]

FLOOR = (214, 216, 212, 255)
WALL = (232, 234, 231, 226)
DARK_WALL = (212, 214, 211, 230)
PARAPET = (220, 223, 219, 245)
GLASS = (191, 222, 232, 185)
HEADER = (225, 227, 224, 210)
LINE = (90, 90, 90, 255)


@dataclass
class Face:
    pts: list[Point3]
    fill: Color
    outline: Color = LINE
    width: int = 2

    @property
    def order(self) -> float:
        return sum(x + y + z * 0.12 for x, y, z in self.pts) / len(self.pts)


@dataclass
class Label:
    text: str
    point: Point3


@dataclass
class Measurement:
    name: str
    a: Point2
    b: Point2
    expected_mm: float
    offset: Point2 = (0, 0)

    @property
    def measured_mm(self) -> float:
        return math.dist(self.a, self.b)


@dataclass
class RequiredEdge:
    name: str
    a: Point2
    b: Point2
    expected_mm: float

    @property
    def measured_mm(self) -> float:
        return math.dist(self.a, self.b)


@dataclass
class Scene:
    name: str
    filename: str
    expected_bbox: tuple[float, float] | None = None
    faces: list[Face] = field(default_factory=list)
    floors: list[list[Point2]] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    lines: list[tuple[Point3, Point3, Color, int]] = field(default_factory=list)
    dots: list[tuple[Point3, Color, int]] = field(default_factory=list)
    overlays: list[Face] = field(default_factory=list)
    cameras: list[tuple[Point2, Point2]] = field(default_factory=list)
    measurements: list[Measurement] = field(default_factory=list)
    required_edges: list[RequiredEdge] = field(default_factory=list)

    def floor(self, pts: list[Point2]):
        self.floors.append(pts)
        self.faces.append(Face([(x, y, 0) for x, y in pts], FLOOR, (112, 112, 112, 255), 3))

    def wall(self, a: Point2, b: Point2, z0=0, z1=WALL_H, fill: Color = WALL, outline: Color = LINE, width=2):
        self.faces.append(Face([(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)], fill, outline, width))

    def window_wall(self, a: Point2, b: Point2, sill=900, head=1900):
        self.wall(a, b, 0, sill, PARAPET)
        self.wall(a, b, sill, head, GLASS, (80, 105, 110, 230), 2)
        self.wall(a, b, head, WALL_H, HEADER)

    def threshold(self, a: Point2, b: Point2, color=(150, 95, 50, 255), width=5):
        self.lines.append(((a[0], a[1], 8), (b[0], b[1], 8), color, width))

    def label(self, text: str, point: Point3):
        self.labels.append(Label(text, point))

    def camera(self, at: Point2, look: Point2):
        self.cameras.append((at, look))
        self.dots.append(((at[0], at[1], 35), (210, 0, 0, 255), 9))
        self.lines.append(((at[0], at[1], 35), (look[0], look[1], 35), (210, 0, 0, 220), 4))

    def measure(self, name: str, a: Point2, b: Point2, expected_mm: float, offset: Point2 = (0, 0)):
        self.measurements.append(Measurement(name, a, b, expected_mm, offset))

    def require_floor_edge(self, name: str, a: Point2, b: Point2, expected_mm: float):
        self.required_edges.append(RequiredEdge(name, a, b, expected_mm))

    def toilet(self, origin: Point2):
        x, y = origin
        z = 1320
        self.overlays.append(Face([(x - 210, y - 150, z), (x + 210, y - 150, z), (x + 210, y + 150, z), (x - 210, y + 150, z)], (238, 238, 235, 255), LINE, 2))
        self.overlays.append(Face([(x - 140, y - 85, z + 70), (x + 140, y - 85, z + 70), (x + 140, y + 105, z + 70), (x - 140, y + 105, z + 70)], (247, 247, 245, 255), LINE, 2))

    def basin(self, origin: Point2):
        x, y = origin
        z = 1260
        self.overlays.append(Face([(x - 180, y - 130, z), (x + 180, y - 130, z), (x + 180, y + 130, z), (x - 180, y + 130, z)], (244, 244, 241, 255), LINE, 2))

    def shower_zone(self, a: Point2, b: Point2):
        x0, y0 = a
        x1, y1 = b
        z = 1120
        self.overlays.append(Face([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], (204, 220, 224, 170), (80, 105, 110, 220), 2))

    def render(self, stamp_text: str | None = None, stamp_pass: bool | None = None):
        audit = self.audit_dimensions()
        if not audit["pass"]:
            raise ValueError(f"whitebox dimension audit failed for {self.filename}: {audit['violations']}")

        im = Image.new("RGBA", (W, H), (248, 248, 245, 255))
        draw = ImageDraw.Draw(im, "RGBA")

        points = [p for face in self.faces for p in face.pts]
        points += [p for face in self.overlays for p in face.pts]
        points += self._dimension_points()
        points += [a for a, _, _, _ in self.lines] + [b for _, b, _, _ in self.lines]
        points += [label.point for label in self.labels] + [p for p, _, _ in self.dots]
        raw = [self._raw(p) for p in points]
        minx, maxx = min(x for x, _ in raw), max(x for x, _ in raw)
        miny, maxy = min(y for _, y in raw), max(y for _, y in raw)
        scale = COMMON_SCALE
        ox = (W - (minx + maxx) * scale) / 2
        oy = (H - (miny + maxy) * scale) / 2

        def project(p: Point3):
            x, y = self._raw(p)
            return (ox + x * scale, oy + y * scale)

        for face in sorted(self.faces, key=lambda f: f.order):
            pts = [project(p) for p in face.pts]
            draw.polygon(pts, fill=face.fill)
            draw.line(pts + [pts[0]], fill=face.outline, width=face.width)

        for a, b, color, width in self.lines:
            draw.line((project(a), project(b)), fill=color, width=width)

        for face in sorted(self.overlays, key=lambda f: f.order):
            pts = [project(p) for p in face.pts]
            draw.polygon(pts, fill=face.fill)
            draw.line(pts + [pts[0]], fill=face.outline, width=face.width)

        for p, color, radius in self.dots:
            x, y = project(p)
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)

        self._draw_dimensions(draw, project)
        self._draw_title(draw)
        self._draw_audit_stamp(draw, audit, stamp_text, stamp_pass)
        for label in self.labels:
            x, y = project(label.point)
            draw.rectangle((x - 5, y - 18, x + len(label.text) * 7 + 8, y + 5), fill=(255, 255, 255, 210))
            draw.text((x, y - 15), label.text, fill=(120, 40, 25, 255))

        rgb = im.convert("RGB")
        out = OUT_DIR / self.filename
        variant = out.with_name(f"{out.stem}-{AUDIT_VARIANT}{out.suffix}")
        rgb.save(out)
        rgb.save(variant)
        return variant

    @staticmethod
    def _raw(p: Point3):
        x, y, z = p
        return ((x - y) * 0.78, (x + y) * 0.42 - z * 0.72)

    def _draw_title(self, draw):
        draw.rectangle((36, 32, 36 + len(self.name) * 9 + 20, 64), fill=(255, 255, 255, 220))
        draw.text((46, 41), self.name, fill=(60, 60, 60, 255))

    def floor_bbox(self):
        if not self.floors:
            return None
        xs = [x for floor in self.floors for x, _ in floor]
        ys = [y for floor in self.floors for _, y in floor]
        return (min(xs), min(ys), max(xs), max(ys))

    def audit_dimensions(self):
        violations = []
        bbox = self.floor_bbox()
        if not bbox:
            violations.append({"element": "floor_missing", "evidence": "Scene has no floor polygon."})
            return {"scene": self.filename, "pass": False, "violations": violations}

        x0, y0, x1, y1 = bbox
        actual_w = x1 - x0
        actual_d = y1 - y0
        measurements = {
            "bbox_mm": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)],
            "actual_width_mm": round(actual_w, 1),
            "actual_depth_mm": round(actual_d, 1),
            "fixed_render_scale": COMMON_SCALE,
            "measurement_segments": [],
            "required_floor_edges": [],
        }

        if self.expected_bbox:
            exp_w, exp_d = self.expected_bbox
            width_error = abs(actual_w - exp_w) / max(1, exp_w)
            depth_error = abs(actual_d - exp_d) / max(1, exp_d)
            aspect_error = abs((actual_w / actual_d) - (exp_w / exp_d)) / max(0.001, exp_w / exp_d)
            measurements.update({
                "expected_width_mm": exp_w,
                "expected_depth_mm": exp_d,
                "width_error_pct": round(width_error * 100, 3),
                "depth_error_pct": round(depth_error * 100, 3),
                "aspect_error_pct": round(aspect_error * 100, 3),
            })
            if width_error > DIM_TOLERANCE:
                violations.append({"element": "width_mismatch", "evidence": f"width {actual_w:.1f}mm != expected {exp_w:.1f}mm"})
            if depth_error > DIM_TOLERANCE:
                violations.append({"element": "depth_mismatch", "evidence": f"depth {actual_d:.1f}mm != expected {exp_d:.1f}mm"})
            if aspect_error > DIM_TOLERANCE:
                violations.append({"element": "aspect_mismatch", "evidence": f"aspect {actual_w / actual_d:.3f} != expected {exp_w / exp_d:.3f}"})

        x_unit = self._raw((1000, 0, 0))
        y_unit = self._raw((0, 1000, 0))
        origin = self._raw((0, 0, 0))
        x_proj = math.dist(origin, x_unit)
        y_proj = math.dist(origin, y_unit)
        projection_error = abs(x_proj - y_proj) / max(1, x_proj)
        measurements.update({
            "x_axis_projected_px_per_1000mm": round(x_proj * COMMON_SCALE, 3),
            "y_depth_projected_px_per_1000mm": round(y_proj * COMMON_SCALE, 3),
            "axis_projection_error_pct": round(projection_error * 100, 3),
        })
        if projection_error > 0.01:
            violations.append({"element": "depth_projection_mismatch", "evidence": "x and depth axes are not using the same whitebox scale."})

        if not self.measurements:
            violations.append({"element": "measurement_segments_missing", "evidence": "No explicit measured segments were declared for this scene."})
        for segment in self.measurements:
            measured = segment.measured_mm
            segment_error = abs(measured - segment.expected_mm) / max(1, segment.expected_mm)
            ax, ay = self._raw((segment.a[0], segment.a[1], 0))
            bx, by = self._raw((segment.b[0], segment.b[1], 0))
            projected_px = math.dist((ax, ay), (bx, by)) * COMMON_SCALE
            expected_projected_px = segment.expected_mm * x_proj * COMMON_SCALE / 1000
            projected_error = abs(projected_px - expected_projected_px) / max(1, expected_projected_px)
            measurements["measurement_segments"].append({
                "name": segment.name,
                "start": [round(segment.a[0], 1), round(segment.a[1], 1)],
                "end": [round(segment.b[0], 1), round(segment.b[1], 1)],
                "expected_mm": round(segment.expected_mm, 1),
                "measured_mm": round(measured, 1),
                "segment_error_pct": round(segment_error * 100, 3),
                "projected_px": round(projected_px, 3),
                "expected_projected_px": round(expected_projected_px, 3),
                "projected_error_pct": round(projected_error * 100, 3),
            })
            if segment_error > DIM_TOLERANCE:
                violations.append({
                    "element": "measurement_segment_mismatch",
                    "evidence": f"{segment.name}: measured {measured:.1f}mm != expected {segment.expected_mm:.1f}mm",
                })
            if projected_error > DIM_TOLERANCE:
                violations.append({
                    "element": "dimension_line_projection_mismatch",
                    "evidence": f"{segment.name}: drawn dimension projects {projected_px:.1f}px != expected {expected_projected_px:.1f}px",
                })

        actual_edges = set()
        for floor in self.floors:
            for a, b in zip(floor, floor[1:] + floor[:1]):
                actual_edges.add(self._edge_key(a, b))
                actual_edges.add(self._edge_key(b, a))
        if not self.required_edges:
            violations.append({"element": "required_floor_edges_missing", "evidence": "No floor edge manifest was declared for this scene."})
        for edge in self.required_edges:
            measured = edge.measured_mm
            edge_error = abs(measured - edge.expected_mm) / max(1, edge.expected_mm)
            present = self._edge_key(edge.a, edge.b) in actual_edges
            measurements["required_floor_edges"].append({
                "name": edge.name,
                "start": [round(edge.a[0], 1), round(edge.a[1], 1)],
                "end": [round(edge.b[0], 1), round(edge.b[1], 1)],
                "expected_mm": round(edge.expected_mm, 1),
                "measured_mm": round(measured, 1),
                "edge_error_pct": round(edge_error * 100, 3),
                "present_in_floor_polygon": present,
            })
            if not present:
                violations.append({
                    "element": "required_floor_edge_missing",
                    "evidence": f"{edge.name}: required floor edge {edge.a}->{edge.b} is not present in the floor polygon.",
                })
            if edge_error > DIM_TOLERANCE:
                violations.append({
                    "element": "required_floor_edge_length_mismatch",
                    "evidence": f"{edge.name}: measured {measured:.1f}mm != expected {edge.expected_mm:.1f}mm",
                })

        for i, (camera, look) in enumerate(self.cameras, start=1):
            cx, cy = camera
            lx, ly = look
            if not (x0 <= cx <= x1 and y0 <= cy <= y1):
                violations.append({"element": "camera_outside_floor", "evidence": f"camera #{i} {camera} is outside bbox {bbox}"})
            if not (x0 <= lx <= x1 and y0 <= ly <= y1):
                violations.append({"element": "look_at_outside_floor", "evidence": f"look_at #{i} {look} is outside bbox {bbox}"})

        return {
            "scene": self.filename,
            "pass": not violations,
            "violations": violations,
            "measurements": measurements,
        }

    def _dimension_points(self):
        points = []
        for segment in self.required_edges:
            ox, oy = (0, 0)
            points.extend([
                (segment.a[0] + ox, segment.a[1] + oy, 20),
                (segment.b[0] + ox, segment.b[1] + oy, 20),
            ])
        return points

    def _draw_dimensions(self, draw, project):
        dim_color = (0, 82, 204, 255)
        endpoint_color = (255, 126, 0, 255)
        tick = 70
        for segment in self.required_edges:
            ox, oy = (0, 0)
            a = (segment.a[0] + ox, segment.a[1] + oy)
            b = (segment.b[0] + ox, segment.b[1] + oy)
            pa = project((a[0], a[1], 20))
            pb = project((b[0], b[1], 20))
            draw.line((pa, pb), fill=dim_color, width=7)
            for px, py in (pa, pb):
                draw.ellipse((px - 8, py - 8, px + 8, py + 8), fill=endpoint_color)

            dx = segment.b[0] - segment.a[0]
            dy = segment.b[1] - segment.a[1]
            length = max(1, math.hypot(dx, dy))
            nx, ny = -dy / length, dx / length
            for p in (a, b):
                draw.line((
                    project((p[0] - nx * tick, p[1] - ny * tick, 20)),
                    project((p[0] + nx * tick, p[1] + ny * tick, 20)),
                ), fill=dim_color, width=4)

            mid = ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
            self._draw_small_label(draw, f"{segment.name} {round(segment.expected_mm)}mm", mid)

    def _draw_audit_stamp(self, draw, audit, stamp_text: str | None = None, stamp_pass: bool | None = None):
        ok = audit["pass"] if stamp_pass is None else stamp_pass
        text = stamp_text or ("REAL-EDGE AUDITED V4 PASS" if ok else "REAL-EDGE AUDIT FAIL")
        fill = (236, 252, 239, 230) if ok else (255, 236, 236, 230)
        text_fill = (36, 90, 50, 255) if ok else (150, 42, 28, 255)
        draw.rectangle((36, 68, 36 + len(text) * 8 + 24, 100), fill=fill)
        draw.text((46, 78), text, fill=text_fill)

    @staticmethod
    def _draw_small_label(draw, text, point):
        x, y = point
        draw.rectangle((x - 48, y - 16, x + len(text) * 7 + 16, y + 12), fill=(255, 255, 255, 235))
        draw.text((x - 40, y - 12), text, fill=(0, 70, 170, 255))

    @staticmethod
    def _edge_key(a: Point2, b: Point2):
        return (round(a[0], 3), round(a[1], 3), round(b[0], 3), round(b[1], 3))


def add_rect_shell(scene: Scene, w: int, d: int, door_wall: str, door_span: tuple[int, int] | None = None):
    scene.floor([(0, 0), (w, 0), (w, d), (0, d)])
    spans = {
        "north": ((0, 0), (w, 0)),
        "east": ((w, 0), (w, d)),
        "south": ((0, d), (w, d)),
        "west": ((0, 0), (0, d)),
    }
    for side, (a, b) in spans.items():
        if side == door_wall and door_span:
            lo, hi = door_span
            if side in {"north", "south"}:
                y = a[1]
                if lo > 0:
                    scene.wall((0, y), (lo, y))
                if hi < w:
                    scene.wall((hi, y), (w, y))
                scene.threshold((lo, y), (hi, y))
            else:
                x = a[0]
                if lo > 0:
                    scene.wall((x, 0), (x, lo))
                if hi < d:
                    scene.wall((x, hi), (x, d))
                scene.threshold((x, lo), (x, hi))
        else:
            scene.wall(a, b)


def fact_mm(facts: dict, room: str, segment: str, default: float) -> float:
    value = facts.get(room, {}).get(segment)
    return float(value) if value is not None else float(default)


def study(facts: dict | None = None):
    facts = facts or {}
    w = fact_mm(facts, "THE STUDY", "window wall inner clear edge", 2895)
    left_depth = fact_mm(facts, "THE STUDY", "left interior wall depth", 4229)
    right_depth = fact_mm(facts, "THE STUDY", "right interior wall depth", left_depth)
    d = max(left_depth, right_depth)
    s = Scene(f"THE STUDY whitebox - {round(w)} x {round(d)}, wide bi-fold opening", "study-whitebox-traced-axon.png", (w, d))
    s.floor([(0, 0), (w, 0), (w, d), (0, d)])
    s.wall((0, 0), (0, d))
    s.wall((w, 0), (w, d))
    # Use the interior window-wall face from L0.5, not the exterior printed span.
    s.window_wall((0, 0), (w, 0))
    # Homeowner brief: glass-and-timber bi-fold creates an open-concept edge to
    # Living/Dining. Keep only jambs/returns, not a bedroom-like front wall.
    s.wall((0, d), (220, d), fill=DARK_WALL)
    s.wall((w - 220, d), (w, d), fill=DARK_WALL)
    s.threshold((220, d), (w - 220, d))
    s.camera((w * 0.52, d - 450), (w * 0.55, 280))
    s.measure("width", (0, 0), (w, 0), w, (0, -280))
    s.measure("depth", (0, 0), (0, d), d, (-260, 0))
    s.require_floor_edge("study interior window edge", (0, 0), (w, 0), w)
    s.require_floor_edge("study left interior wall", (0, 0), (0, d), d)
    s.require_floor_edge("study right interior wall", (w, 0), (w, d), d)
    s.label("north window band", (700, 0, 2750))
    s.label("wide bi-fold opening to Living/Dining", (360, d, 260))
    s.label("party wall to kitchen", (0, 1850, 2200))
    s.label("party wall to Bedroom 1", (w, 1850, 2200))
    return s


def bedroom_1(facts: dict | None = None):
    facts = facts or {}
    w = fact_mm(facts, "BEDROOM 1", "north interior clear edge", 2896)
    d = fact_mm(facts, "BEDROOM 1", "west interior wall depth", 4654)
    window_opening = fact_mm(facts, "BEDROOM 1", "window opening clear width", w * 0.75)
    right_return = fact_mm(facts, "BEDROOM 1", "solid return beside window", max(0, w - window_opening))
    if window_opening + right_return > w:
        right_return = max(0, w - window_opening)
    s = Scene(f"BEDROOM 1 whitebox - {round(w)} x {round(d)}", "bedroom-1-whitebox-traced-axon.png", (w, d))
    s.floor([(0, 0), (w, 0), (w, d), (0, d)])
    s.wall((0, 0), (0, d))
    s.window_wall((0, 0), (window_opening, 0))
    if window_opening < w:
        s.wall((window_opening, 0), (w, 0), fill=DARK_WALL)
    s.wall((w, 0), (w, d))
    s.wall((914, d), (w, d))
    s.threshold((0, d), (914, d))
    s.camera((620, d - 380), (1420, 360))
    # The right-side window return is a solid wall segment on the north wall,
    # not an L-shaped floor notch.
    s.measure("width", (0, 0), (w, 0), w, (0, -210))
    s.measure("depth", (0, 0), (0, d), d, (-260, 0))
    s.measure("window opening", (0, 0), (window_opening, 0), window_opening, (0, -260))
    s.measure("solid return", (window_opening, 0), (w, 0), right_return, (0, 170))
    s.require_floor_edge("bedroom1 north interior edge", (0, 0), (w, 0), w)
    s.require_floor_edge("bedroom1 west depth edge", (0, 0), (0, d), d)
    s.require_floor_edge("bedroom1 east depth edge", (w, 0), (w, d), d)
    s.label("north window band", (520, 0, 2750))
    s.label(f"{round(right_return)} solid return beside window", (window_opening + 20, 0, 2100))
    s.label("hall doorway", (90, d, 220))
    s.label("party wall to Study", (0, 2000, 2200))
    return s


def bedroom_2():
    w, d = 2896, 4528
    s = Scene("BEDROOM 2 whitebox - 2896 x 4528", "bedroom-2-whitebox-traced-axon.png", (w, d))
    s.floor([(0, 0), (w, 0), (w, d), (0, d)])
    s.wall((0, 0), (0, d))
    s.wall((w, 0), (w, d))
    s.wall((914, 0), (w, 0))
    s.threshold((0, 0), (914, 0))
    s.window_wall((180, d), (2500, d))
    s.camera((620, 380), (1420, d - 320))
    s.measure("width", (0, d), (w, d), 2896, (0, 260))
    s.measure("depth", (0, 0), (0, d), 4528, (-260, 0))
    s.require_floor_edge("bedroom2 south window edge", (0, d), (w, d), 2896)
    s.require_floor_edge("bedroom2 west party wall", (0, 0), (0, d), 4528)
    s.require_floor_edge("bedroom2 east exterior wall", (w, 0), (w, d), 4528)
    s.label("south window band", (520, d, 2750))
    s.label("hall doorway", (90, 0, 220))
    s.label("party wall to Living/Dining", (0, 2100, 2200))
    s.label("east exterior wall", (w, 2100, 2200))
    return s


def kitchen():
    block_w, service_d, wet_w, room_d = 4648, 2553, 1863, 4229
    s = Scene("KITCHEN + SERVICE HALLWAY whitebox - open concept", "kitchen-whitebox-traced-axon.png", (block_w, room_d))
    # L-shaped usable area: the plan label "BALCONY" is treated as an enclosed
    # service hallway; the lower-right area is the open-concept kitchen.
    s.floor([(0, 0), (block_w, 0), (block_w, room_d), (wet_w, room_d), (wet_w, service_d), (0, service_d)])
    s.window_wall((250, 0), (block_w - 250, 0))
    s.wall((0, 0), (0, service_d))
    s.wall((block_w, 0), (block_w, room_d))
    # Wet block boundary inside the service/kitchen zone.
    s.wall((0, service_d), (250, service_d))
    s.threshold((250, service_d), (760, service_d))
    s.wall((760, service_d), (1020, service_d))
    s.threshold((1020, service_d), (1700, service_d))
    s.wall((1700, service_d), (wet_w, service_d))
    s.wall((wet_w, service_d), (wet_w, room_d), fill=DARK_WALL)
    # Open concept: no enclosing wall between kitchen and Living/Dining.
    s.threshold((wet_w, room_d), (block_w, room_d))
    s.camera((3350, room_d - 420), (2050, 500))
    s.measure("service width", (0, 0), (block_w, 0), 4648, (0, -270))
    s.measure("block depth", (block_w, 0), (block_w, room_d), 4229, (260, 0))
    s.measure("wet block width", (0, service_d), (wet_w, service_d), 1863, (0, 210))
    s.require_floor_edge("service hallway window edge", (0, 0), (block_w, 0), 4648)
    s.require_floor_edge("kitchen open living edge", (wet_w, room_d), (block_w, room_d), block_w - wet_w)
    s.require_floor_edge("wet block return", (wet_w, service_d), (wet_w, room_d), room_d - service_d)
    s.label("enclosed service hallway, not balcony", (560, 0, 2750))
    s.label("W.C. + Bath doors from service hallway", (250, service_d, 2050))
    s.label("open concept threshold to Living/Dining", (wet_w + 280, room_d, 230))
    s.label("counter wall zone", (block_w, 2050, 2100))
    return s


def bath_wc():
    wc_w, bath_w, d = 838, 1025, 1676
    w = wc_w + bath_w
    s = Scene("BATH + W.C. whitebox - toilet included", "bath-wc-whitebox-traced-axon.png", (w, d))
    s.floor([(0, 0), (w, 0), (w, d), (0, d)])
    s.wall((0, 0), (0, d))
    s.wall((w, 0), (w, d))
    s.wall((wc_w, 0), (wc_w, d), fill=DARK_WALL)
    s.wall((0, d), (w, d))
    s.wall((0, 0), (240, 0))
    s.threshold((240, 0), (760, 0))
    s.wall((760, 0), (wc_w + 160, 0))
    s.threshold((wc_w + 160, 0), (wc_w + 820, 0))
    s.wall((wc_w + 820, 0), (w, 0))
    s.toilet((wc_w * 0.48, d - 430))
    s.basin((wc_w + 300, 520))
    s.shower_zone((wc_w + 155, d - 620), (w - 130, d - 120))
    s.camera((wc_w + 520, 180), (wc_w + 520, d - 220))
    s.measure("width", (0, 0), (w, 0), 1863, (0, -220))
    s.measure("depth", (0, 0), (0, d), 1676, (-220, 0))
    s.measure("W.C.", (0, d), (wc_w, d), 838, (0, 170))
    s.measure("Bath", (wc_w, d), (w, d), 1025, (0, 170))
    s.require_floor_edge("wet block width", (0, 0), (w, 0), 1863)
    s.require_floor_edge("wet block depth", (0, 0), (0, d), 1676)
    s.label("W.C. compartment: toilet pan", (120, d - 420, 1350))
    s.label("Bath compartment: basin + shower", (wc_w + 210, d - 520, 1600))
    s.label("doors from kitchen", (250, 0, 210))
    return s


def write_contact_sheet(generated: list[Path]):
    names = [
        OUT_DIR / "living-dining-whitebox-traced-axon.png",
        *generated,
    ]
    existing = [p for p in names if p.exists()]
    if not existing:
        return None

    cards = []
    for path in existing:
        im = Image.open(path).convert("RGB")
        im.thumbnail((520, 360))
        card = Image.new("RGB", (560, 410), "white")
        card.paste(im, ((560 - im.width) // 2, 34))
        draw = ImageDraw.Draw(card)
        draw.text((18, 12), path.name, fill=(35, 35, 35))
        cards.append(card)

    cols = 2
    rows = (len(cards) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 560, rows * 410), (245, 245, 242))
    for i, card in enumerate(cards):
        sheet.paste(card, ((i % cols) * 560, (i // cols) * 410))

    out = OUT_DIR / "unit-whitebox-contact-sheet.png"
    variant = OUT_DIR / f"unit-whitebox-contact-sheet-{AUDIT_VARIANT}.png"
    sheet.save(out)
    sheet.save(variant)
    return variant


def load_dimension_gate():
    if not DIMENSION_MANIFEST.exists():
        return {
            "pass": False,
            "manifest": str(DIMENSION_MANIFEST),
            "status": "missing",
            "violations": [{
                "element": "dimension_decomposition_missing",
                "evidence": f"Run `npm run decompose:dimensions` before whitebox audit: {DIMENSION_MANIFEST}",
            }],
        }

    manifest = json.loads(DIMENSION_MANIFEST.read_text(encoding="utf-8"))
    review_items = manifest.get("critical_review_required", [])
    identity_items = manifest.get("room_identity_violations", [])
    status = manifest.get("status")
    violations = []
    if status != "verified":
        violations.append({
            "element": "dimension_decomposition_unverified",
            "evidence": f"L0.5 manifest status is {status}; {len(review_items)} segment(s) require review; {len(identity_items)} room identity issue(s).",
        })
    for item in identity_items:
        requested_room = item.get("requested_room", "unknown room")
        plan_label = item.get("plan_label", "unknown plan label")
        evidence = item.get("evidence", "")
        violations.append({
            "element": "room_identity_unverified",
            "evidence": f"{requested_room}: selected crop is plan label {plan_label}. {evidence}",
        })
    for item in review_items:
        room = item.get("room", "unknown room")
        segment = item.get("segment", "unknown segment")
        note = item.get("note", "")
        violations.append({
            "element": "unverified_floorplan_segment",
            "evidence": f"{room} / {segment}: {note}",
        })

    return {
        "pass": not violations,
        "manifest": str(DIMENSION_MANIFEST),
        "overview": manifest.get("overview"),
        "status": status,
        "room_identity_violations": identity_items,
        "critical_review_required": review_items,
        "violations": violations,
    }


def load_dimension_facts():
    if not DIMENSION_MANIFEST.exists():
        return {}
    manifest = json.loads(DIMENSION_MANIFEST.read_text(encoding="utf-8"))
    facts = {}
    for room in manifest.get("rooms", []):
        room_name = room.get("room")
        if not room_name or room.get("identity_status") != "verified":
            continue
        facts[room_name] = {}
        for segment in room.get("segments", []):
            name = segment.get("name")
            computed = segment.get("computed_mm")
            if name is not None and computed is not None and segment.get("effective_feeds_whitebox", segment.get("feeds_whitebox")):
                facts[room_name][name] = computed
    return facts


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dimension_gate = load_dimension_gate()
    dimension_facts = load_dimension_facts()
    scenes = [kitchen()]
    if "THE STUDY" in dimension_facts:
        scenes.append(study(dimension_facts))
    scenes.extend([bedroom_1(dimension_facts), bedroom_2(), bath_wc()])
    audits = [scene.audit_dimensions() for scene in scenes]
    audit_doc = {
        "pass": all(audit["pass"] for audit in audits) and dimension_gate["pass"],
        "projection_contract": {
            "scale_mode": "fixed",
            "scale": COMMON_SCALE,
            "dimension_tolerance_pct": DIM_TOLERANCE * 100,
        },
        "dimension_decomposition_gate": dimension_gate,
        "rooms": audits,
    }
    audit_path = OUT_DIR / "whitebox-dimension-audit.json"
    audit_path.write_text(json.dumps(audit_doc, indent=2), encoding="utf-8")
    print(audit_path)
    allow_unverified = "--allow-unverified-dimensions" in sys.argv
    if not audit_doc["pass"] and not allow_unverified:
        print(json.dumps(audit_doc, indent=2), file=sys.stderr)
        raise SystemExit(1)
    if "--audit-only" in sys.argv:
        return

    outputs = []
    stamp_text = None if dimension_gate["pass"] else "L0.5 DIMENSION REVIEW REQUIRED"
    stamp_pass = None if dimension_gate["pass"] else False
    for scene in scenes:
        out = scene.render(stamp_text=stamp_text, stamp_pass=stamp_pass)
        outputs.append(out)
        print(out)
    contact_sheet = write_contact_sheet(outputs)
    if contact_sheet:
        print(contact_sheet)


if __name__ == "__main__":
    main()
