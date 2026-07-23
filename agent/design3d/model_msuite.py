#!/usr/bin/env python3
"""Stage 0 — 3qr master-suite: facts.json -> room_model.json (mm, 3D build spec).

Coordinate system: X east (mm), Y north (mm), Z up (mm). Origin at plan px
(434, 944) = SW-most interior corner of the suite polygon. Every element
carries `ref` (facts.json provenance) or class "proposed" (design decision,
user-visible, overridable).

Usage: python3 model_msuite.py <facts.json> <out_dir>
"""
import json, sys, pathlib

FACTS = pathlib.Path(sys.argv[1])
OUT = pathlib.Path(sys.argv[2])
facts = json.loads(FACTS.read_text())
unit = facts["unit"]
MMPX = unit["calibration"]["mm_per_px"]          # 17.05, isotropic
room = [r for r in facts["rooms"] if r["key"] == "master-suite"][0]

OX, OY = 434, 944                                 # px origin (SW)
def X(px): return round((px - OX) * MMPX, 1)
def Y(py): return round((OY - py) * MMPX, 1)

poly = [[X(x), Y(y)] for x, y in room["polygon_px"]]

CEIL = room["ceiling_height_mm"]                  # 2600, frame:ceiling-slab
WALL_T = 200                                      # nominal shell thickness (render-only)
SILL, HEAD = 1000, 2400                           # sill: hdb-norm parapet ~1.0m; head 2400: assumption, needs_site_verify

# --- openings (each tied to the interior-face polygon edge it sits on) ---
# door: facts doors_windows[2] "south x596-662", width 914; edge (590,905)-(662,905)
door = {
    "id": "door-entry", "kind": "door",
    "edge": [[X(590), Y(905)], [X(662), Y(905)]],
    "span": [X(596), X(596) + 914], "axis": "x", "face_y": Y(905),
    "z": [0, 2150], "width_mm": 914,
    "swing": "inward-west",                       # proposed: opens into room, west leaf (pocket wardrobe sits east)
    "ref": ["facts:rooms.master-suite.doors_windows[2]", "int:hack-plan"],
}
# BR1 window (corrected 2026-07-22): 1671mm at x600-698 on the MAIN north face y698 —
# 半窗+返回 pattern; the x699-763 recess is a solid-walled high-cabinet niche, NOT a window bay.
w_br1 = {
    "id": "win-br1", "kind": "window",
    "edge": [[X(699), Y(698)], [X(434), Y(698)]],
    "span": [X(600), X(600) + 1671], "axis": "x", "face_y": Y(698),
    "z": [SILL, HEAD], "width_mm": 1671,
    "parapet_recess_mm": 324,                     # same section as BR3 (ink rows y673/688-692/695-696)
    "ref": ["facts:rooms.master-suite.doors_windows[0] (corrected)", "facts:corrections[2026-07-22]"],
}
# BR3 window: full-width between column faces x440-585 = niche[2] run 2472, face y698
w_br3 = {
    "id": "win-br3", "kind": "window",
    "edge": [[X(699), Y(698)], [X(434), Y(698)]],
    "span": [X(440), X(440) + 2472], "axis": "x", "face_y": Y(698),
    "z": [SILL, HEAD], "width_mm": 2472,
    "parapet_recess_mm": 324,                     # under-window cabinet band, niche[2]
    "ref": ["facts:rooms.master-suite.cabinet_niches[2]", "facts:...doors_windows[1]"],
}
# bricked former BR3 door x545-593 -> plain wall now (doors_windows[3]); no opening emitted.

openings = [door, w_br1, w_br3]

# --- MEP layer (stage 2) -----------------------------------------------------
# user facts (2026-07-22 brief): compressor outside BR1 window; no ceiling light;
# floor lamp. facts.mep: dry room, FCU on internal wall + condensate drain.
# FCU above the entrance door (industry-preferred spot; A4/R-UX-1 compliant: throw is north,
# the direct-throw footprint never crosses the bed). Rejected: niche-back position — its throw
# band overlapped the pillow zone by ~350mm at 1.2-2.6m (contractor verbal rule + industry guidance; provenance in ux_rules.json).
# Trunking: boxed high-level run east along the south wall, north along the solid-RC east wall
# (no windows to cross), into the niche back to the penetration — monotonic fall 2160->2060.
mep = {
    "class": "proposed", "needs_site_verify": True,
    "no_ceiling_luminaire": True,                 # user P1: 无主灯/无吊灯 — hard constraint
    "fcu": {"id": "mep-fcu", "wall": "south wall, above entrance door", "face_y": Y(905),
            "x": [2990, 3880], "z": [2160, 2390], "depth": 220, "throw": [0, 1],
            "note": "shifted east clear of the x2663-2963 beam-risk band (fcu top 2390 > worst-case beam soffit 2300)",
            "ref": ["facts:rooms.master-suite.mep", "user:P1-2026-07-22", "ux_rules:R-UX-1/R-UX-3",
                    "facts:rooms.master-suite.beams_columns (2026-07-22)"]},
    "penetration": {"id": "mep-pen", "at": [4740, Y(662)], "z": 200,
                    "note": "LOW-LEVEL core through niche back wall, hidden behind the niche cabinet plinth; verify on site"},
    "trunking": [   # boxes [x0,y0,z0,x1,y1,z1]; installer-standard route: vertical drop beside the
        # door frame, then skirting/plinth-level run (hidden behind wardrobe plinth + headboard)
        {"id": "mep-trunk-a", "box": [3775, Y(905), 210, 3860, Y(905) + 90, 2160],
         "note": "vertical boxed drop beside door east jamb (standard above-door FCU detail)"},
        {"id": "mep-trunk-b", "box": [3860, 515, 165, 5609, 605, 250], "attach": "fur-wardrobe-pocket",
         "note": "skirting run along south step + pocket-wardrobe plinth front"},
        {"id": "mep-trunk-c", "box": [5519, 605, 120, 5609, 4718, 205],
         "note": "east-wall skirting run, hidden behind the 220mm headboard offset"},
        {"id": "mep-trunk-d", "box": [4700, 4718, 120, 5609, Y(662), 205],
         "note": "along niche back wall behind cabinet plinth to the low-level pen"},
    ],
    "compressor": {"id": "mep-compressor", "box": [4560, Y(662) + 250, 300, 5510, Y(662) + 600, 1000],
                   "note": "on external bracket outside the north facade, beside the BR1 window — user-stated",
                   "ref": ["user:P1-2026-07-22"]},
    "sockets": [  # [x, y, z, wall-normal] small boxes ON wall faces
        {"id": "skt-bed-n", "p": [X(770) - 10, 3500, 300], "face": "east", "use": "bedside north"},
        {"id": "skt-bed-s", "p": [X(770) - 10, 1500, 300], "face": "east", "use": "bedside south + floor lamp"},
        {"id": "skt-closet", "p": [X(434) + 10, 2000, 300], "face": "west", "use": "walk-in closet"},
        {"id": "skt-br3", "p": [X(500), Y(698) - 10, 300], "face": "north", "use": "dresser/vanity zone"},
    ],
}

# --- structural risk layer: drawn from stage 1 as RISK volumes, never as facts ---
# The 宁缺勿错 rule bans unconfirmed beams as FACT geometry; a MEDIUM-probability beam
# over the demolished bed1/bed3 partition (line X≈2813, RC column at its north end)
# must still be VISIBLE in every render and the design must survive the beam-present
# outcome. Worst case: 300mm downstand (soffit 2300), 300mm wide band.
risk_elements = [
    {"id": "risk-beam", "class": "risk", "box": [2663, Y(905), 2300, 2963, Y(698), CEIL],
     "needs_site_verify": True,
     "note": "possible N-S frame beam over removed partition x599px; probability MEDIUM; tap-test/borescope BEFORE hacking; if confirmed, box as bulkhead — design below is valid in BOTH outcomes",
     "ref": ["facts:rooms.master-suite.beams_columns (2026-07-22)"]},
]

# --- furnishing layer (stage 3) — design_plan, all "proposed" ---------------
# P1 (user 2026-07-22): dark walnut floor; warm off-white walls + under-window
# cabinets; light walnut closet joinery; walk-in closet; full-length light-coffee
# blackout + sheer curtains; no main light, floor lamp.
BED_W, BED_L = 1520, 1900                         # queen
bed_head_x = X(770) - 220                         # 220 off the east wall: skirting-level aircon trunking runs hidden behind the headboard
bed_cy = (Y(711) + Y(877)) / 2 + 100              # +100 north: balances south pass-through (786) vs north bedside (776)
furniture = [
    {"id": "fur-bed", "kind": "bed", "box": [bed_head_x - BED_L, bed_cy - BED_W/2, 0, bed_head_x, bed_cy + BED_W/2, 550],
     "color": "linen", "note": "queen, head on east wall between jogs y711-877"},
    {"id": "fur-headboard", "kind": "bed", "box": [bed_head_x - 80, bed_cy - BED_W/2, 0, bed_head_x, bed_cy + BED_W/2, 1150],
     "color": "light-walnut"},
    {"id": "fur-nightstand-n", "kind": "table", "box": [bed_head_x - 450, bed_cy + BED_W/2 + 80, 0, bed_head_x, bed_cy + BED_W/2 + 530, 500], "color": "light-walnut"},
    {"id": "fur-nightstand-s", "kind": "table", "box": [bed_head_x - 450, bed_cy - BED_W/2 - 530, 0, bed_head_x, bed_cy - BED_W/2 - 80, 500], "color": "light-walnut"},
    # walk-in closet: former BR3 south zone; furniture-defined (no new wall -> no permit item)
    {"id": "fur-closet-west", "kind": "closet", "box": [X(441), Y(914), 0, X(441) + 600, Y(790), 2400],
     "color": "light-walnut", "note": "600-deep wardrobe run; back at x441 jog line (SW column bump), small void behind upper half"},
    {"id": "fur-closet-south", "kind": "closet", "box": [X(441) + 600, Y(914), 0, X(575), Y(914) + 600, 2400],
     "color": "light-walnut", "note": "600-deep run on south wall, stops 900+ clear of door line"},
    {"id": "fur-closet-return", "kind": "closet", "box": [X(575), Y(914), 0, X(590), Y(914) + 600, 2400],
     "color": "light-walnut", "note": "end panel return at closet mouth"},
    # pocket wardrobe: SE niche x669-770 y914-944 (cabinet_niches[0])
    {"id": "fur-wardrobe-pocket", "kind": "closet", "box": [X(669), Y(944), 0, X(763), Y(914), 2400],
     "color": "light-walnut", "note": "front face at x763 jog so the unit clears the east-wall step",
     "ref": ["facts:rooms.master-suite.cabinet_niches[0]"]},
    {"id": "fur-wardrobe-filler", "kind": "closet", "box": [X(763), Y(944), 0, X(770), Y(926), 2400],
     "color": "light-walnut", "note": "boxed-in filler closing the 119x307 dead pocket east of the wardrobe to the wall (standard joinery end detail)"},
    # under-window cabinets — warm off-white (P1)
    {"id": "fur-cab-br3", "kind": "cabinet", "box": [X(440), Y(698), 0, X(440) + 2472, Y(698) + 324, SILL],
     "color": "off-white", "note": "fills 324 parapet band outward of wall face, front flush, h=sill",
     "ref": ["facts:rooms.master-suite.cabinet_niches[2]"]},
    {"id": "fur-cab-br1", "kind": "cabinet", "box": [X(600), Y(698), 0, X(600) + 1671, Y(698) + 324, SILL],
     "color": "off-white", "note": "BR1 under-window cabinet in the newly-registered 324 band, front flush, h=sill",
     "ref": ["facts:rooms.master-suite.cabinet_niches[3] (added 2026-07-22)"]},
    {"id": "fur-cab-bay", "kind": "closet", "box": [X(699) + 3, Y(698) + 3, 0, X(763) - 103, Y(662) - 108, 2400],
     "color": "light-walnut", "note": "tall cabinet in the beside-window niche (高柜位), 1950 doors + boxed-in top filler to ceiling line; back 108mm + east side 100mm held off the niche walls for the plinth-level trunking",
     "ref": ["facts:rooms.master-suite.cabinet_niches[1] (corrected: high-cabinet recess, not window bay)"]},
    {"id": "fur-pelmet-br1", "kind": "cabinet", "box": [2740, Y(698) - 180, 2280, 4510, Y(698), CEIL],
     "color": "off-white", "note": "curtain pelmet box under the beam-risk band: soffit 2280, boxes the beam if confirmed / hides the dropped track if not — valid in both site outcomes",
     "ref": ["facts:rooms.master-suite.beams_columns (2026-07-22)"]},
    {"id": "fur-lamp", "kind": "lamp", "box": [5150, 800, 0, 5500, 1150, 1500],
     "color": "brass", "note": "floor lamp SE of bed beside east wall — the only luminaire (P1); 660mm from skt-bed-s"},
    {"id": "fur-rug", "kind": "rug", "box": [bed_head_x - BED_L - 600, bed_cy - BED_W/2 - 250, 0, bed_head_x - 400, bed_cy + BED_W/2 + 400, 15],
     "color": "ivory", "note": "south margin 250 keeps the rug out of the door-swing arc (15mm pile would drag the leaf)"},
]
curtains = [  # full-length drop to floor (P1). Rendered in DAY state: sheer drawn across
    # the span, blackout stacked as a 300mm column at each end.
    # BR1 track crosses the beam-risk band -> track mounts at 2280 (under worst-case soffit)
    # inside a pelmet box 2280-2600 (fur-pelmet-br1): beam confirmed -> pelmet boxes it in;
    # no beam -> pelmet hides the track. Valid in both site outcomes.
    {"id": "cur-br1-black-l", "win": "win-br1", "box": [2740, Y(698) - 110, 20, 3040, Y(698) - 60, 2280], "layer": "blackout"},
    {"id": "cur-br1-black-r", "win": "win-br1", "box": [4210, Y(698) - 110, 20, 4510, Y(698) - 60, 2280], "layer": "blackout"},
    {"id": "cur-br1-sheer", "win": "win-br1", "box": [2740, Y(698) - 160, 20, 4510, Y(698) - 130, 2280], "layer": "sheer"},
    # BR3 track stays at ceiling; its east stack is trimmed to x2640 to stay clear of the band.
    {"id": "cur-br3-black-l", "win": "win-br3", "box": [15, Y(698) - 110, 20, 315, Y(698) - 60, CEIL - 20], "layer": "blackout"},
    {"id": "cur-br3-black-r", "win": "win-br3", "box": [2490, Y(698) - 110, 20, 2640, Y(698) - 60, CEIL - 20], "layer": "blackout"},
    {"id": "cur-br3-sheer", "win": "win-br3", "box": [15, Y(698) - 160, 20, 2640, Y(698) - 130, CEIL - 20], "layer": "sheer"},
]

palette = {  # P1 palette, used for stage-3 visual base + stage-4 prompt
    "floor": "dark-walnut", "walls": "warm-off-white", "ceiling": "white",
    "closet": "light-walnut", "under-window-cabinet": "warm-off-white",
    "curtain": "light-coffee-blackout + white-sheer", "lighting": "no ceiling light; floor lamp only",
}

cams = [  # 7 perspective views + audit top — full-room angular coverage, gated by AV (viewmap.py)
    {"id": "cam-entry", "eye": [X(620), Y(898), 1500], "target": [5100, 3600, 1250], "fov_deg": 74,
     "note": "from door looking NE: bed, bay window + curtains, floor lamp"},
    {"id": "cam-ne", "eye": [X(756), Y(716), 1550], "target": [X(470), Y(890), 1150], "fov_deg": 68,
     "note": "from NE corner looking SW to walk-in closet"},
    {"id": "cam-br3", "eye": [X(452), Y(712), 1550], "target": [X(700), Y(890), 1100], "fov_deg": 68,
     "note": "from BR3 window corner looking SE: closet mouth + door + pocket wardrobe"},
    {"id": "cam-sw", "eye": [850, 1500, 1550], "target": [5300, 4300, 1150], "fov_deg": 74,
     "note": "from closet mouth looking NE: bed, bay niche, curtains, east wall"},
    {"id": "cam-se", "eye": [5250, 680, 1560], "target": [700, 4100, 1100], "fov_deg": 74,
     "note": "from SE corner (pocket wardrobe) looking NW: BR3 window wall, closet front"},
    {"id": "cam-n-mid", "eye": [2750, 3850, 1550], "target": [2900, 350, 1150], "fov_deg": 74,
     "note": "from window band looking S: door wall, FCU above door, trunk drop, closet+wardrobe"},
    {"id": "cam-w-mid", "eye": [430, 3350, 1550], "target": [5600, 2300, 1100], "fov_deg": 72,
     "note": "west wall looking E: bed elevation, headboard wall, nightstands, lamp"},
    {"id": "cam-niche", "eye": [4200, 2500, 1600], "target": [5050, 4550, 1350], "fov_deg": 74,
     "note": "over the bed foot looking N: bay niche frontal (full-height cabinet), BR1 curtain edge, east wall"},
    {"id": "cam-top", "ortho": True, "eye": [(X(434)+X(770))/2, (Y(944)+Y(662))/2, 8000],
     "target": [(X(434)+X(770))/2, (Y(944)+Y(662))/2, 0], "scale": 6500, "note": "audit top view"},
]

model = {
    "meta": {"source_facts": str(FACTS), "room": "master-suite", "mm_per_px": MMPX,
             "origin_px": [OX, OY], "axes": "X east, Y north, Z up (mm)",
             "identity_status": room["identity_status"],
             "beams": "NOT modelled — facts.beams_columns needs_site_verify; rule: unconfirmed beams are never drawn",
             "beam_risk": {"line_x_mm": round((599 - OX) * MMPX, 1),
                           "claim": room["beams_columns"]["claim"][:180],
                           "needs_site_verify": True,
                           "ref": ["facts:rooms.master-suite.beams_columns (2026-07-22)"]}},
    "ceiling_mm": CEIL, "wall_t": WALL_T,
    "polygon": poly, "polygon_px": room["polygon_px"],
    "area_sqft_facts": room["area_sqft"],
    "openings": openings, "mep": mep, "risk_elements": risk_elements,
    "furniture": furniture, "curtains": curtains,
    "palette": palette, "cameras": cams,
}
(OUT / "room_model.json").write_text(json.dumps(model, ensure_ascii=False, indent=1))
print("room_model.json written:", OUT / "room_model.json")
print("polygon verts:", len(poly), "| openings:", [o["id"] for o in openings])
