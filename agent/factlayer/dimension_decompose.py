#!/usr/bin/env python3
"""Floor-plan dimension decomposition skill.

This creates the missing L0.5 fact layer between "uploaded floor plan" and
"3D whitebox": calibrated dimensions, derived-but-reviewable edge lengths,
room crops, and annotated evidence images. It is deliberately conservative:
unclear / unprinted segments are recorded with evidence and review_required
instead of being promoted into structural facts.

Current implementation is deterministic for the RenoGent demo plan. The output
schema is intentionally general so a later OCR/vision extractor can populate
the same manifest.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUT_DIR = Path("demo/inbox")
VARIANT = "dimension-decomposition-v1"


Point = tuple[float, float]

SHORT_LABELS = {
    "full window-side edge": "full window edge",
    "printed structural bay width": "printed bay",
    "window wall inner clear edge": "inside window wall",
    "north interior clear edge": "north inside edge",
    "window opening clear width": "window opening",
    "solid return beside window": "solid return",
    "west interior wall depth": "west inside depth",
    "left party wall depth": "left wall depth",
    "right party wall depth": "right wall depth",
    "left interior wall depth": "left inside depth",
    "right interior wall depth": "right inside depth",
    "wide bi-fold edge": "bi-fold edge",
    "bi-fold opening clear edge": "bi-fold opening",
    "printed room width": "printed width",
    "window-side edge before return": "window edge",
    "short vertical jog at window": "window jog",
    "right return beside window": "right return",
    "west party wall depth": "west wall depth",
    "south window-side edge": "south window edge",
    "service hallway full edge": "service edge",
    "open concept kitchen edge to living": "open kitchen edge",
}


@dataclass
class Calibration:
    name: str
    axis: str
    p1: Point
    p2: Point
    printed_mm: float
    source_label: str
    confidence: str = "high"

    @property
    def pixel_len(self) -> float:
        return abs(self.p2[0] - self.p1[0]) if self.axis == "x" else abs(self.p2[1] - self.p1[1])

    @property
    def mm_per_px(self) -> float:
        return self.printed_mm / self.pixel_len


@dataclass
class Segment:
    room: str
    name: str
    p1: Point
    p2: Point
    source: str
    expected_mm: float | None = None
    formula: str | None = None
    confidence: str = "medium"
    review_required: bool = False
    note: str = ""
    measurement_kind: str = "unknown"
    feeds_whitebox: bool = False
    boundary_check: str = "none"


@dataclass
class RoomCrop:
    room: str
    box: tuple[int, int, int, int]
    segments: list[Segment]
    interior_polygon: list[Point] | None = None
    plan_label: str = ""
    identity_status: str = "verified"
    identity_note: str = ""


def font(size=18):
    for path in ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def segment_len_px(seg: Segment) -> float:
    return math.dist(seg.p1, seg.p2)


def point_on_segment(p: Point, a: Point, b: Point, tolerance=2.5) -> bool:
    px, py = p
    ax, ay = a
    bx, by = b
    seg_len = math.dist(a, b)
    if seg_len == 0:
        return math.dist(p, a) <= tolerance
    cross = abs((px - ax) * (by - ay) - (py - ay) * (bx - ax)) / seg_len
    if cross > tolerance:
        return False
    dot = (px - ax) * (bx - ax) + (py - ay) * (by - ay)
    return -tolerance <= dot <= seg_len * seg_len + tolerance


def point_in_or_on_polygon(p: Point, polygon: list[Point], tolerance=2.5) -> bool:
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if point_on_segment(p, a, b, tolerance):
            return True

    x, y = p
    inside = False
    j = len(polygon) - 1
    for i, pi in enumerate(polygon):
        xi, yi = pi
        xj, yj = polygon[j]
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def segment_inside_room(seg: Segment, polygon: list[Point]) -> tuple[bool, str]:
    points = [
        ("start", seg.p1),
        ("mid", ((seg.p1[0] + seg.p2[0]) / 2, (seg.p1[1] + seg.p2[1]) / 2)),
        ("end", seg.p2),
    ]
    outside = [name for name, point in points if not point_in_or_on_polygon(point, polygon)]
    if outside:
        return False, f"{', '.join(outside)} point(s) fall outside the declared interior envelope"
    return True, ""


def scale_for_segment(seg: Segment, scale_x: float, scale_y: float) -> float:
    dx = abs(seg.p2[0] - seg.p1[0])
    dy = abs(seg.p2[1] - seg.p1[1])
    if dx >= dy:
        return scale_x
    return scale_y


def derived_mm(seg: Segment, scale_x: float, scale_y: float) -> float:
    # Orthogonal HDB drawings: use dominant axis scale. Short jogs are still
    # axis-aligned in this plan; diagonal use is intentionally not supported.
    return segment_len_px(seg) * scale_for_segment(seg, scale_x, scale_y)


def draw_label(draw, xy, text, fill=(0, 70, 170, 255), text_fill=(20, 40, 70, 255), fnt=None, bounds=None):
    fnt = fnt or font(16)
    x, y = xy
    if bounds:
        max_w, max_h = bounds
        bbox0 = draw.textbbox((0, 0), text, font=fnt)
        text_w = bbox0[2] - bbox0[0]
        text_h = bbox0[3] - bbox0[1]
        x = min(max(8, x), max(8, max_w - text_w - 14))
        y = min(max(8, y), max(8, max_h - text_h - 12))
    bbox = draw.textbbox((x, y), text, font=fnt)
    draw.rectangle((bbox[0] - 6, bbox[1] - 4, bbox[2] + 6, bbox[3] + 4), fill=(255, 255, 255, 235), outline=fill, width=2)
    draw.text((x, y), text, fill=text_fill, font=fnt)


def draw_segment(draw, seg: Segment, scale_x: float, scale_y: float, offset=(0, 0), bounds=None):
    ox, oy = offset
    p1 = (seg.p1[0] - ox, seg.p1[1] - oy)
    p2 = (seg.p2[0] - ox, seg.p2[1] - oy)
    color = (235, 80, 30, 255) if seg.review_required else (0, 82, 204, 255)
    if seg.measurement_kind == "structural_span":
        color = (55, 150, 80, 255)
    draw.line((p1, p2), fill=color, width=5)
    for p in (p1, p2):
        draw.ellipse((p[0] - 5, p[1] - 5, p[0] + 5, p[1] + 5), fill=(255, 126, 0, 255))
    mm = seg.expected_mm if seg.expected_mm is not None else derived_mm(seg, scale_x, scale_y)
    suffix = " VERIFY" if seg.review_required else ""
    mid = ((p1[0] + p2[0]) / 2 + 8, (p1[1] + p2[1]) / 2 - 18)
    name = SHORT_LABELS.get(seg.name, seg.name)
    draw_label(draw, mid, f"{name}: {round(mm)}mm{suffix}", fill=color, text_fill=color, fnt=font(14), bounds=bounds)


def build_demo_decomposition():
    # Coordinates are on demo/inbox/plan-1783836724077-cropped.jpg.
    # They are kept in one place because this is the L0.5 fact record for the
    # demo unit, not hidden inside the renderer.
    calibrations = [
        Calibration("top total width", "x", (164, 83), (793, 83), 10439, "10439"),
        Calibration("service/stairs block width", "x", (164, 112), (444, 112), 4648, "4648"),
        Calibration("study width", "x", (444, 112), (619, 112), 2895, "2895"),
        Calibration("bedroom 1 width", "x", (619, 112), (793, 112), 2896, "2896"),
        Calibration("bay width", "x", (263, 967), (432, 967), 2800, "2800"),
        Calibration("bedroom 1 height", "y", (863, 210), (863, 496), 4654, "4654"),
        Calibration("bedroom 2 height", "y", (863, 498), (863, 775), 4528, "4528"),
        Calibration("wet block height", "y", (56, 304), (56, 406), 1676, "1676"),
    ]

    # Critical non-obvious dimensions are explicitly listed. When the plan does
    # not print the segment value, source stays pixel_derived and review_required
    # stays true.
    study = [
        Segment(
            "THE STUDY",
            "printed structural bay width",
            (444, 112),
            (619, 112),
            "printed_span",
            2895,
            "top printed 2895",
            "high",
            False,
            "Printed outside dimension; use for scale/evidence, not as an interior room edge.",
            "structural_span",
            False,
        ),
        Segment(
            "THE STUDY",
            "window wall inner clear edge",
            (449, 252),
            (615, 252),
            "pixel_derived",
            None,
            None,
            "medium",
            True,
            "Inside face below the window band. This replaces the previous line that ran through the exterior/window zone.",
            "interior_clear",
            True,
            "inside_or_boundary",
        ),
        Segment(
            "THE STUDY",
            "left interior wall depth",
            (449, 252),
            (449, 489),
            "pixel_derived",
            None,
            None,
            "medium",
            True,
            "Interior face-to-threshold depth; not the external printed structural span.",
            "interior_clear",
            True,
            "inside_or_boundary",
        ),
        Segment(
            "THE STUDY",
            "right interior wall depth",
            (615, 252),
            (615, 489),
            "pixel_derived",
            None,
            None,
            "medium",
            True,
            "Interior face-to-threshold depth; explicitly avoids the outside window line.",
            "interior_clear",
            True,
            "inside_or_boundary",
        ),
        Segment(
            "THE STUDY",
            "bi-fold opening clear edge",
            (449, 489),
            (615, 489),
            "pixel_derived",
            None,
            None,
            "medium",
            True,
            "Opening edge only; verify against door swing/bi-fold symbol before locking.",
            "opening_clear",
            False,
            "inside_or_boundary",
        ),
    ]
    bedroom1_x_scale = 2896 / (793 - 619)
    bedroom1 = [
        Segment(
            "BEDROOM 1",
            "printed room width",
            (619, 112),
            (793, 112),
            "printed_span",
            2896,
            "top printed 2896",
            "high",
            False,
            "Printed structural bay width; not an interior clear wall edge.",
            "structural_span",
            False,
        ),
        Segment(
            "BEDROOM 1",
            "north interior clear edge",
            (622, 252),
            (790, 252),
            "pixel_derived",
            round((790 - 622) * bedroom1_x_scale, 1),
            "local top scale: 2896mm / 174px",
            "medium",
            True,
            "Inside face of the north wall. The window and right return sit on this wall; they are not a floor-plan notch.",
            "interior_clear",
            True,
            "inside_or_boundary",
        ),
        Segment(
            "BEDROOM 1",
            "window opening clear width",
            (622, 252),
            (746, 252),
            "pixel_derived",
            round((746 - 622) * bedroom1_x_scale, 1),
            "local top scale: 2896mm / 174px",
            "medium",
            True,
            "Window opening along the interior wall face; not a room boundary.",
            "window_opening",
            False,
            "inside_or_boundary",
        ),
        Segment(
            "BEDROOM 1",
            "solid return beside window",
            (746, 252),
            (790, 252),
            "pixel_derived",
            round((790 - 746) * bedroom1_x_scale, 1),
            "local top scale: 2896mm / 174px",
            "medium",
            True,
            "Solid wall return beside the window on the same north wall; do not convert it into an L-shaped floor notch.",
            "solid_wall_return",
            False,
            "inside_or_boundary",
        ),
        Segment(
            "BEDROOM 1",
            "west interior wall depth",
            (622, 252),
            (622, 509),
            "pixel_derived",
            None,
            None,
            "medium",
            True,
            "Interior clear depth from the north wall face to the hall threshold; avoids the exterior/window band.",
            "interior_clear",
            True,
            "inside_or_boundary",
        ),
    ]
    bedroom2 = [
        Segment("BEDROOM 2", "south window-side edge", (619, 775), (793, 775), "printed_span", 2896, "top printed 2896 transferred to same bay width", "medium", True),
        Segment("BEDROOM 2", "room depth", (793, 498), (793, 775), "printed_span", 4528, "right-side printed 4528", "high"),
    ]
    wet = [
        Segment("BATH + W.C.", "W.C. width", (185, 304), (235, 304), "printed_span", 838, "838"),
        Segment("BATH + W.C.", "Bath width", (235, 304), (297, 304), "printed_span", 1025, "1025"),
        Segment("BATH + W.C.", "wet block depth", (164, 304), (164, 406), "printed_span", 1676, "1676"),
    ]
    kitchen = [
        Segment("KITCHEN + SERVICE HALLWAY", "service hallway full edge", (164, 225), (444, 225), "printed_span", 4648, "top printed 4648", "high"),
        Segment("KITCHEN + SERVICE HALLWAY", "wet block edge", (164, 406), (297, 406), "pixel_derived", None, None, "medium", True),
        Segment("KITCHEN + SERVICE HALLWAY", "open concept kitchen edge to living", (297, 502), (444, 502), "pixel_derived", None, None, "medium", True),
    ]

    rooms = [
        RoomCrop("KITCHEN + SERVICE HALLWAY", (130, 170, 465, 535), kitchen),
        RoomCrop(
            "THE STUDY",
            (398, 128, 685, 555),
            study,
            [(449, 252), (615, 252), (615, 489), (449, 489)],
            "BEDROOM 3",
            "rejected_by_user",
            "This crop was previously used as THE STUDY, but the user rejected that room identity mapping. Treat it only as evidence that the selected floor-plan area is BEDROOM 3, not as THE STUDY dimensions.",
        ),
        RoomCrop("BEDROOM 1", (580, 120, 875, 545), bedroom1, [(622, 252), (790, 252), (790, 509), (622, 509)]),
        RoomCrop("BEDROOM 2", (585, 500, 825, 795), bedroom2),
        RoomCrop("BATH + W.C.", (145, 285, 330, 430), wet),
    ]
    return calibrations, rooms


def manifest_for(plan_path: Path, calibrations: list[Calibration], rooms: list[RoomCrop], out_dir: Path):
    high_x = [c.mm_per_px for c in calibrations if c.axis == "x" and c.confidence == "high"]
    high_y = [c.mm_per_px for c in calibrations if c.axis == "y" and c.confidence == "high"]
    scale_x = sum(high_x) / len(high_x)
    scale_y = sum(high_y) / len(high_y)

    cal_doc = []
    for c in calibrations:
        residual = (c.mm_per_px - (scale_x if c.axis == "x" else scale_y)) / (scale_x if c.axis == "x" else scale_y)
        cal_doc.append({
            **asdict(c),
            "pixel_len": round(c.pixel_len, 3),
            "mm_per_px": round(c.mm_per_px, 4),
            "scale_residual_pct": round(residual * 100, 2),
        })

    room_docs = []
    critical_review = []
    semantic_violations = []
    room_identity_violations = []
    for room in rooms:
        identity_ok = room.identity_status == "verified"
        if not identity_ok:
            room_identity_violations.append({
                "requested_room": room.room,
                "plan_label": room.plan_label,
                "status": room.identity_status,
                "evidence": room.identity_note,
            })
        seg_docs = []
        for seg in room.segments:
            mm = seg.expected_mm if seg.expected_mm is not None else derived_mm(seg, scale_x, scale_y)
            semantic_status = "not_checked"
            semantic_note = ""
            effective_feeds_whitebox = bool(seg.feeds_whitebox and identity_ok)
            if not identity_ok:
                semantic_status = "identity_blocked"
                semantic_note = "Skipped because room identity is not verified."
            elif seg.boundary_check == "inside_or_boundary":
                if not room.interior_polygon:
                    semantic_status = "failed"
                    semantic_note = "Segment requires an interior envelope, but the room has none."
                else:
                    ok, semantic_note = segment_inside_room(seg, room.interior_polygon)
                    semantic_status = "ok" if ok else "failed"
                if semantic_status != "ok":
                    semantic_violations.append({
                        "room": seg.room,
                        "segment": seg.name,
                        "measurement_kind": seg.measurement_kind,
                        "feeds_whitebox": seg.feeds_whitebox,
                        "evidence": semantic_note,
                    })
            if effective_feeds_whitebox and seg.measurement_kind != "interior_clear":
                semantic_status = "failed"
                semantic_note = "Only interior_clear measurements may feed whitebox room geometry."
                semantic_violations.append({
                    "room": seg.room,
                    "segment": seg.name,
                    "measurement_kind": seg.measurement_kind,
                    "feeds_whitebox": seg.feeds_whitebox,
                    "evidence": semantic_note,
                })
            doc = {
                **asdict(seg),
                "pixel_len": round(segment_len_px(seg), 3),
                "computed_mm": round(mm, 1),
                "used_scale": "x" if abs(seg.p2[0] - seg.p1[0]) >= abs(seg.p2[1] - seg.p1[1]) else "y",
                "semantic_status": semantic_status,
                "semantic_note": semantic_note,
                "effective_feeds_whitebox": effective_feeds_whitebox,
            }
            seg_docs.append(doc)
            if identity_ok and seg.review_required:
                critical_review.append({"room": seg.room, "segment": seg.name, "note": seg.note})
        crop_name = f"{plan_path.stem}-{room.room.lower().replace(' + ', '-').replace(' ', '-')}-dimension-crop.png"
        room_docs.append({
            "room": room.room,
            "plan_label": room.plan_label,
            "identity_status": room.identity_status,
            "identity_note": room.identity_note,
            "crop": str(out_dir / crop_name),
            "crop_box": room.box,
            "interior_polygon": room.interior_polygon,
            "segments": seg_docs,
        })

    status = "verified"
    if room_identity_violations:
        status = "room_identity_unverified"
    elif semantic_violations:
        status = "measurement_semantics_failed"
    elif critical_review:
        status = "needs_human_dimension_review"

    return {
        "plan": str(plan_path),
        "variant": VARIANT,
        "status": status,
        "scale": {
            "x_mm_per_px": round(scale_x, 4),
            "y_mm_per_px": round(scale_y, 4),
            "x_reference_count": len(high_x),
            "y_reference_count": len(high_y),
            "note": "Use axis-specific scale because the source is a phone screenshot / exported image, not a distortion-corrected CAD file.",
        },
        "calibration_segments": cal_doc,
        "rooms": room_docs,
        "critical_review_required": critical_review,
        "semantic_violations": semantic_violations,
        "room_identity_violations": room_identity_violations,
    }


def render_outputs(plan_path: Path, out_dir: Path, calibrations: list[Calibration], rooms: list[RoomCrop], manifest: dict):
    im = Image.open(plan_path).convert("RGBA")
    scale_x = manifest["scale"]["x_mm_per_px"]
    scale_y = manifest["scale"]["y_mm_per_px"]

    overview = im.copy()
    od = ImageDraw.Draw(overview, "RGBA")
    for c in calibrations:
        color = (55, 150, 80, 255) if c.confidence == "high" else (220, 120, 40, 255)
        od.line((c.p1, c.p2), fill=color, width=4)
        draw_label(od, ((c.p1[0] + c.p2[0]) / 2 + 5, (c.p1[1] + c.p2[1]) / 2 - 20), f"CAL {c.source_label}", fill=color, bounds=overview.size)
    for room in rooms:
        x0, y0, x1, y1 = room.box
        identity_ok = room.identity_status == "verified"
        outline = (0, 82, 204, 255) if identity_ok else (210, 50, 35, 255)
        od.rectangle((x0, y0, x1, y1), outline=outline, width=3)
        if identity_ok and room.interior_polygon:
            od.line(room.interior_polygon + [room.interior_polygon[0]], fill=(20, 150, 80, 230), width=4)
        if identity_ok:
            draw_label(od, (x0 + 6, y0 + 6), room.room, fill=(0, 82, 204, 255), bounds=overview.size)
            for seg in room.segments:
                draw_segment(od, seg, scale_x, scale_y, bounds=overview.size)
        else:
            draw_label(od, (x0 + 6, y0 + 6), f"{room.room} ID BLOCKED", fill=outline, text_fill=outline, bounds=overview.size)
            draw_label(od, (x0 + 6, y0 + 32), f"selected plan label: {room.plan_label}", fill=outline, text_fill=outline, fnt=font(13), bounds=overview.size)

    overview_out = out_dir / f"{plan_path.stem}-{VARIANT}-overview.png"
    overview.convert("RGB").save(overview_out)

    for room in rooms:
        crop = im.crop(room.box).convert("RGBA")
        draw = ImageDraw.Draw(crop, "RGBA")
        identity_ok = room.identity_status == "verified"
        if identity_ok:
            draw_label(draw, (10, 10), room.room, fill=(0, 82, 204, 255), fnt=font(18), bounds=crop.size)
        else:
            draw_label(draw, (10, 10), f"{room.room}: IDENTITY BLOCKED", fill=(210, 50, 35, 255), text_fill=(210, 50, 35, 255), fnt=font(18), bounds=crop.size)
            draw_label(draw, (10, 40), f"this crop is plan label {room.plan_label}", fill=(210, 50, 35, 255), text_fill=(210, 50, 35, 255), fnt=font(14), bounds=crop.size)
        if identity_ok and room.interior_polygon:
            local_poly = [(x - room.box[0], y - room.box[1]) for x, y in room.interior_polygon]
            draw.line(local_poly + [local_poly[0]], fill=(20, 150, 80, 230), width=4)
        if identity_ok:
            for seg in room.segments:
                draw_segment(draw, seg, scale_x, scale_y, offset=(room.box[0], room.box[1]), bounds=crop.size)
        crop_name = f"{plan_path.stem}-{room.room.lower().replace(' + ', '-').replace(' ', '-')}-dimension-crop.png"
        crop.convert("RGB").save(out_dir / crop_name)
    return overview_out


def main(argv: list[str]) -> int:
    plan_path = Path(argv[1]) if len(argv) > 1 else OUT_DIR / "plan-1783836724077-cropped.jpg"
    out_dir = OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    if not plan_path.exists():
        print(f"missing plan image: {plan_path}", file=sys.stderr)
        return 2

    calibrations, rooms = build_demo_decomposition()
    manifest = manifest_for(plan_path, calibrations, rooms, out_dir)
    overview = render_outputs(plan_path, out_dir, calibrations, rooms, manifest)
    manifest["overview"] = str(overview)
    manifest_path = out_dir / f"{plan_path.stem}-{VARIANT}-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(manifest_path)
    print(overview)
    if manifest["status"] != "verified":
        print(f"status={manifest['status']} review_items={len(manifest['critical_review_required'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
