#!/usr/bin/env python3
"""Deterministic Living/Dining whitebox render.

This intentionally avoids image-generation for the structure pass. The goal is
to prove the room geometry first: openings, window/parapet, and the 2800 recess.
Once this shell is approved, it can become the structural reference for the
renovation/style pass.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from PIL import Image, ImageDraw


OUT_DIR = Path("demo/inbox")
WALL_H = 2.6


Point3 = tuple[float, float, float]
Point2 = tuple[float, float]


def add(a: Point3, b: Point3) -> Point3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a: Point3, b: Point3) -> Point3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(a: Point3, s: float) -> Point3:
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a: Point3, b: Point3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Point3, b: Point3) -> Point3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def norm(a: Point3) -> Point3:
    length = math.sqrt(dot(a, a))
    return (a[0] / length, a[1] / length, a[2] / length)


@dataclass
class Camera:
    pos: Point3
    target: Point3
    focal: float = 520
    cx: float = 700
    cy: float = 545

    def __post_init__(self):
        self.forward = norm(sub(self.target, self.pos))
        world_up = (0.0, 0.0, 1.0)
        self.right = norm(cross(self.forward, world_up))
        self.up = norm(cross(self.right, self.forward))

    def project(self, p: Point3) -> Point2 | None:
        rel = sub(p, self.pos)
        z = dot(rel, self.forward)
        if z <= 0.04:
            return None
        x = dot(rel, self.right)
        y = dot(rel, self.up)
        return (self.cx + self.focal * x / z, self.cy - self.focal * y / z)

    def depth(self, p: Point3) -> float:
        return dot(sub(p, self.pos), self.forward)


@dataclass
class Poly:
    pts: list[Point3]
    fill: tuple[int, int, int, int]
    outline: tuple[int, int, int, int] = (105, 105, 105, 255)
    width: int = 2


def rect_wall(x1, y1, x2, y2, z0=0.0, z1=WALL_H, fill=(230, 232, 229, 255)) -> Poly:
    return Poly([(x1, y1, z0), (x2, y2, z0), (x2, y2, z1), (x1, y1, z1)], fill)


def floor_poly() -> list[Point3]:
    # Plan-space metres, schematic but dimensioned against the real plan:
    # - main living/dining bay approx 4.5m deep
    # - bottom 2800 recess represented as a 2.8m wide window/ledge bay
    return [
        (0.00, 0.00, 0.0),
        (4.50, 0.00, 0.0),
        (4.50, 4.52, 0.0),
        (2.80, 4.52, 0.0),
        (2.80, 5.62, 0.0),
        (0.00, 5.62, 0.0),
        (0.00, 0.00, 0.0),
    ]


def shell_polys() -> list[Poly]:
    polys: list[Poly] = []
    polys.append(Poly(floor_poly(), (214, 216, 212, 255), (120, 120, 120, 255), 3))

    wall = (234, 236, 233, 218)
    dark_wall = (212, 214, 211, 230)
    glass = (206, 228, 235, 180)
    parapet = (220, 222, 218, 255)
    header = (218, 220, 216, 255)

    # Left / stairs side: wall segments with main entrance gap in the middle.
    polys += [
        rect_wall(0, 0, 0, 1.85, fill=wall),
        rect_wall(0, 3.15, 0, 5.62, fill=wall),
    ]
    # Top side: kitchen opening at top-left, study/partition walls beyond.
    polys += [
        rect_wall(1.25, 0, 2.65, 0, fill=wall),
        rect_wall(3.25, 0, 4.50, 0, fill=wall),
    ]
    # Right side: bedroom hall opening near the top, bedroom-2 partition below.
    polys += [
        rect_wall(4.50, 0.00, 4.50, 0.72, fill=wall),
        rect_wall(4.50, 1.62, 4.50, 4.52, fill=wall),
    ]
    # Recess / 2800 bay edges.
    polys += [
        rect_wall(0.00, 5.62, 2.80, 5.62, fill=wall),
        rect_wall(2.80, 4.52, 2.80, 5.62, fill=wall),
    ]
    # Far HDB window wall: solid parapet below, glass band, header above.
    polys += [
        rect_wall(2.80, 4.52, 4.50, 4.52, z0=0.0, z1=0.95, fill=parapet),
        rect_wall(2.80, 4.52, 4.50, 4.52, z0=0.95, z1=1.95, fill=glass),
        rect_wall(2.80, 4.52, 4.50, 4.52, z0=1.95, z1=WALL_H, fill=header),
    ]
    # Recess front also gets a parapet/window signal, not balcony floor-to-ceiling glass.
    polys += [
        rect_wall(0.00, 5.62, 2.80, 5.62, z0=0.0, z1=0.95, fill=parapet),
        rect_wall(0.00, 5.62, 2.80, 5.62, z0=0.95, z1=1.95, fill=glass),
        rect_wall(0.00, 5.62, 2.80, 5.62, z0=1.95, z1=WALL_H, fill=header),
    ]

    # Short returns / visible thickness cues around openings.
    polys += [
        rect_wall(0.00, 1.85, 0.22, 1.85, fill=dark_wall),
        rect_wall(0.00, 3.15, 0.22, 3.15, fill=dark_wall),
        rect_wall(4.28, 0.72, 4.50, 0.72, fill=dark_wall),
        rect_wall(4.28, 1.62, 4.50, 1.62, fill=dark_wall),
        rect_wall(1.25, 0.00, 1.25, 0.22, fill=dark_wall),
        rect_wall(2.65, 0.00, 2.65, 0.22, fill=dark_wall),
    ]
    return polys


def draw_perspective(path: Path):
    im = Image.new("RGBA", (1400, 980), (246, 246, 242, 255))
    draw = ImageDraw.Draw(im, "RGBA")
    # Pulled back and slightly above for structure review, not final eye-level
    # decor rendering.
    cam = Camera(pos=(0.70, -0.55, 2.05), target=(3.25, 4.88, 1.20))
    polys = shell_polys()
    polys.sort(key=lambda p: sum(cam.depth(q) for q in p.pts) / len(p.pts), reverse=True)

    for poly in polys:
        projected = [cam.project(p) for p in poly.pts]
        if any(p is None for p in projected):
            continue
        pts = [(int(x), int(y)) for x, y in projected if x is not None]
        draw.polygon(pts, fill=poly.fill)
        draw.line(pts + [pts[0]], fill=poly.outline, width=poly.width, joint="curve")

    # Window mullions: few vertical divisions only, no grille bars.
    for x in (3.35, 3.90):
        for y in (4.52, 5.62):
            p1, p2 = cam.project((x, y, 0.95)), cam.project((x, y, 1.95))
            if p1 and p2:
                draw.line((p1, p2), fill=(95, 115, 120, 230), width=3)

    # Opening labels for structure review, outside final render path.
    labels = [
        ("main entrance / stairs side", (0.05, 2.50, 1.85)),
        ("kitchen opening", (0.72, 0.03, 1.95)),
        ("bedroom hall opening", (4.48, 1.08, 1.95)),
        ("HDB window + parapet", (3.65, 4.50, 2.18)),
        ("2800 recess / bay", (1.40, 5.62, 2.18)),
    ]
    for text, pos in labels:
        p = cam.project(pos)
        if p:
            x, y = int(p[0]), int(p[1])
            draw.rectangle((x - 5, y - 17, x + len(text) * 7 + 8, y + 4), fill=(255, 255, 255, 190))
            draw.text((x, y - 14), text, fill=(120, 40, 25, 255))

    im.convert("RGB").save(path)


def axon_project(p: Point3, scale=72, ox=650, oy=390) -> Point2:
    x, y, z = p
    sx = ox + (x - y) * scale * 0.86
    sy = oy + (x + y) * scale * 0.50 - z * scale
    return (sx, sy)


def draw_axon(path: Path):
    im = Image.new("RGBA", (1250, 950), (247, 247, 244, 255))
    draw = ImageDraw.Draw(im, "RGBA")
    polys = shell_polys()
    polys.sort(key=lambda p: sum(q[0] + q[1] + q[2] for q in p.pts) / len(p.pts))
    for poly in polys:
        pts = [(int(x), int(y)) for x, y in (axon_project(p) for p in poly.pts)]
        draw.polygon(pts, fill=poly.fill)
        draw.line(pts + [pts[0]], fill=poly.outline, width=poly.width)

    # Camera marker.
    cam = axon_project((0.72, 1.10, 0.02))
    look = axon_project((3.35, 4.55, 0.02))
    draw.ellipse((cam[0] - 9, cam[1] - 9, cam[0] + 9, cam[1] + 9), fill=(210, 0, 0, 255))
    draw.line((cam, look), fill=(210, 0, 0, 220), width=4)

    labels = [
        ("main entrance / stairs side", (0.0, 2.50, 2.82)),
        ("kitchen opening", (0.65, 0.0, 2.82)),
        ("bedroom hall opening", (4.50, 1.15, 2.82)),
        ("HDB window band + solid parapet", (3.25, 4.52, 2.82)),
        ("2800 recess / bay, not balcony", (1.35, 5.62, 2.82)),
    ]
    for text, pos in labels:
        x, y = axon_project(pos)
        draw.rectangle((x - 5, y - 18, x + len(text) * 7 + 8, y + 4), fill=(255, 255, 255, 205))
        draw.text((x, y - 15), text, fill=(120, 40, 25, 255))

    im.convert("RGB").save(path)


def draw_traced_axon(path: Path):
    """Plan-traced axonometric shell used as the structure approval reference."""
    im = Image.new("RGBA", (1400, 1000), (248, 248, 245, 255))
    draw = ImageDraw.Draw(im, "RGBA")
    scale = 1.05
    ox, oy = 690, 260
    zscale = 0.72

    def iso(p, z=0):
        x, y = p
        sx = ox + (x - y) * 0.78 * scale
        sy = oy + (x + y) * 0.42 * scale - z * zscale
        return (sx, sy)

    def poly(points, z=0):
        return [iso(p, z) for p in points]

    def wall(a, b, h=160, fill=(232, 234, 231, 225), outline=(90, 90, 90, 255), width=2):
        pts = [iso(a, 0), iso(b, 0), iso(b, h), iso(a, h)]
        draw.polygon(pts, fill=fill)
        draw.line(pts + [pts[0]], fill=outline, width=width)

    def low_wall(a, b, z0=0, z1=62, fill=(220, 223, 219, 245)):
        pts = [iso(a, z0), iso(b, z0), iso(b, z1), iso(a, z1)]
        draw.polygon(pts, fill=fill)
        draw.line(pts + [pts[0]], fill=(95, 95, 95, 255), width=2)

    def glass_band(a, b, z0=62, z1=126):
        pts = [iso(a, z0), iso(b, z0), iso(b, z1), iso(a, z1)]
        draw.polygon(pts, fill=(191, 222, 232, 185))
        draw.line(pts + [pts[0]], fill=(80, 105, 110, 230), width=2)

    floor = [
        (120, 168),
        (320, 168),
        (320, 155),
        (475, 155),
        (475, 220),
        (510, 220),
        (510, 445),
        (582, 445),
        (582, 480),
        (306, 480),
        (306, 594),
        (120, 594),
        (120, 455),
        (98, 455),
        (98, 408),
        (120, 408),
    ]
    draw.polygon(poly(floor, 0), fill=(214, 216, 212, 255))
    draw.line(poly(floor, 0) + [iso(floor[0], 0)], fill=(95, 95, 95, 255), width=3)

    # Stairs/main entrance side.
    wall((120, 168), (120, 352))
    wall((120, 416), (120, 455))
    wall((98, 408), (120, 408), h=120, fill=(212, 214, 211, 230))
    wall((98, 455), (120, 455), h=120, fill=(212, 214, 211, 230))

    # Kitchen/top side and bedroom hall side.
    wall((120, 168), (175, 168), h=135)
    wall((300, 168), (420, 168), h=150)
    wall((475, 220), (475, 445), h=160)
    wall((510, 220), (510, 445), h=145, fill=(226, 228, 225, 210))

    # Living/dining HDB window wall: solid parapet below, glass band above.
    low_wall((306, 445), (582, 445), 0, 58)
    glass_band((306, 445), (582, 445), 58, 120)
    wall((306, 445), (582, 445), h=160, fill=(230, 232, 228, 70), outline=(80, 80, 80, 130), width=1)

    # Recessed 2800 bay, explicitly modelled as window + parapet, not balcony.
    wall((120, 455), (120, 594), h=130)
    wall((306, 480), (306, 594), h=130)
    low_wall((120, 594), (306, 594), 0, 58)
    glass_band((120, 594), (306, 594), 58, 120)
    wall((120, 594), (306, 594), h=155, fill=(230, 232, 228, 70), outline=(80, 80, 80, 130), width=1)

    cam = (235, 245)
    look = (455, 465)
    cam_p = iso(cam)
    look_p = iso(look)
    draw.ellipse((cam_p[0] - 8, cam_p[1] - 8, cam_p[0] + 8, cam_p[1] + 8), fill=(210, 0, 0, 255))
    draw.line((cam_p, look_p), fill=(210, 0, 0, 220), width=4)

    labels = [
        ("main entrance / stairs side", (83, 395), 140),
        ("kitchen opening", (200, 155), 145),
        ("bedroom hall opening", (480, 190), 150),
        ("HDB window wall + parapet", (380, 445), 145),
        ("2800 recessed bay, not balcony", (150, 594), 145),
    ]
    for text, p, z in labels:
        x, y = iso(p, z)
        draw.rectangle((x - 5, y - 18, x + len(text) * 7 + 8, y + 5), fill=(255, 255, 255, 205))
        draw.text((x, y - 15), text, fill=(120, 40, 25, 255))

    im.convert("RGB").save(path)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    draw_traced_axon(OUT_DIR / "living-dining-whitebox-traced-axon.png")
    draw_axon(OUT_DIR / "living-dining-whitebox-axon.png")
    draw_perspective(OUT_DIR / "living-dining-whitebox-perspective.png")
    print(OUT_DIR / "living-dining-whitebox-traced-axon.png")
    print(OUT_DIR / "living-dining-whitebox-axon.png")
    print(OUT_DIR / "living-dining-whitebox-perspective.png")


if __name__ == "__main__":
    main()
