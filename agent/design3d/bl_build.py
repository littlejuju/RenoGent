# Blender headless builder — stages 1(shell)/2(+MEP)/3(+furnishing).
# Run: Blender --background --python bl_build.py -- <room_model.json> <out_root> <stage>
# Units: 1 BU = 1 mm. Deterministic Workbench renders: visual (STUDIO) + id (FLAT).
import bpy, json, sys, math
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

argv = sys.argv[sys.argv.index("--") + 1:]
MODEL, OUT, STAGE = argv[0], argv[1], int(argv[2])
M = json.load(open(MODEL))
POLY = [tuple(p) for p in M["polygon"]]
CEIL, WT = M["ceiling_mm"], M["wall_t"]

# semantic class -> (visual RGBA stage1/2, stage3 palette RGBA, id RGBA)
def pal(name):
    P = {  # class: (early_visual, design_visual, id)
        "wall":    ((0.85, 0.83, 0.80, 1), (0.93, 0.90, 0.84, 1), (0.8, 0.1, 0.1, 1)),
        "floor":   ((0.55, 0.55, 0.55, 1), (0.23, 0.13, 0.08, 1), (0.1, 0.1, 0.8, 1)),
        "ceiling": ((0.95, 0.95, 0.95, 1), (0.96, 0.95, 0.93, 1), (0.8, 0.8, 0.1, 1)),
        "glass":   ((0.65, 0.80, 0.88, 1), (0.65, 0.80, 0.88, 1), (0.1, 0.8, 0.8, 1)),
        "mep":     ((0.90, 0.45, 0.10, 1), (0.88, 0.88, 0.86, 1), (0.9, 0.5, 0.1, 1)),
        "risk":    ((0.80, 0.22, 0.18, 1), (0.80, 0.22, 0.18, 1), (0.4, 0.0, 0.0, 1)),
        "closet":  (None, (0.62, 0.44, 0.28, 1), (0.1, 0.7, 0.1, 1)),
        "boxup":   (None, (0.93, 0.90, 0.84, 1), (0.55, 0.55, 0.95, 1)),
        "cabinet": (None, (0.90, 0.87, 0.80, 1), (0.2, 0.9, 0.2, 1)),
        "bed":     (None, (0.88, 0.85, 0.78, 1), (0.3, 0.6, 0.1, 1)),
        "table":   (None, (0.62, 0.44, 0.28, 1), (0.1, 0.5, 0.3, 1)),
        "lamp":    (None, (0.72, 0.58, 0.30, 1), (1.0, 0.6, 0.8, 1)),
        "rug":     (None, (0.90, 0.88, 0.82, 1), (0.5, 0.9, 0.9, 1)),
        "blackout":(None, (0.72, 0.60, 0.48, 1), (0.7, 0.1, 0.7, 1)),
        "sheer":   (None, (0.96, 0.96, 0.94, 1), (0.9, 0.4, 0.9, 1)),
    }
    return P[name]

def klass(objname):
    for k in ("floor", "ceiling", "glass", "wall", "risk"):
        if objname.startswith(k): return k
    if objname.startswith("mep") or objname.startswith("skt"): return "mep"
    if objname.startswith("cur"):
        return "blackout" if "black" in objname else "sheer"
    return objname.split(":")[1] if ":" in objname else "wall"

def mkmesh(name, verts, faces):
    me = bpy.data.meshes.new(name)
    me.from_pydata([Vector(v) for v in verts], [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob

def box(name, x0, y0, z0, x1, y1, z1):
    v = [(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
    f = [(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
    return mkmesh(name, v, f)

def prism(name, poly2d, z0, z1):
    n = len(poly2d)
    tris = tessellate_polygon([[Vector(p) for p in poly2d]])
    verts = [(x, y, z0) for x, y in poly2d] + [(x, y, z1) for x, y in poly2d]
    faces = [tuple(reversed(t)) for t in tris] + [tuple(i + n for i in t) for t in tris]
    faces += [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
    return mkmesh(name, verts, faces)

def inside(pt, poly=POLY):
    x, y = pt; c = False
    for i in range(len(poly)):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c

# ---------- build shell ----------
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)

prism("floor", POLY, -100, 0)
prism("ceiling", POLY, CEIL, CEIL + 100)

ops_by_edge = {}
for o in M["openings"]:
    e = o["edge"]
    ops_by_edge.setdefault((round(e[0][0]), round(e[0][1]), round(e[1][0]), round(e[1][1])), []).append(o)

n = len(POLY)
for i in range(n):
    a, b = POLY[i], POLY[(i + 1) % n]
    horiz = abs(a[1] - b[1]) < 1e-6
    # outward normal via point test
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    ti = WT + (i % 7) * 0.35        # per-edge thickness jitter kills coplanar z-fighting at corners
    EXT = WT + 2                    # end extension to close outside corners
    if horiz:
        outward = 1 if not inside((mx, my + 5)) else -1
        lo, hi = min(a[0], b[0]), max(a[0], b[0])
        def wallbox(name, s0, s1, z0, z1, off=0.0, t=None):
            y0 = my + outward * off; y1 = my + outward * (off + (t or ti))
            box(name, s0, min(y0, y1), z0, s1, max(y0, y1), z1)
    else:
        outward = 1 if not inside((mx + 5, my)) else -1
        lo, hi = min(a[1], b[1]), max(a[1], b[1])
        def wallbox(name, s0, s1, z0, z1, off=0.0, t=None):
            x0 = mx + outward * off; x1 = mx + outward * (off + (t or ti))
            box(name, min(x0, x1), s0, z0, max(x0, x1), s1, z1)
    key = (round(a[0]), round(a[1]), round(b[0]), round(b[1]))
    ops = sorted(ops_by_edge.get(key, []), key=lambda o: o["span"][0])
    if not ops:
        wallbox(f"wall-e{i:02d}", lo - EXT, hi + EXT, 0, CEIL)
        continue
    cursor = lo - EXT
    for k, o in enumerate(ops):
        s0, s1 = o["span"]; z0, z1 = o["z"]
        if s0 - cursor > 1: wallbox(f"wall-e{i:02d}-seg{k}", cursor, s0, 0, CEIL)
        if z1 < CEIL: wallbox(f"wall-e{i:02d}-header{k}", s0, s1, z1, CEIL)
        if o["kind"] == "window":
            rec = o.get("parapet_recess_mm", 0)
            wallbox(f"wall-e{i:02d}-parapet{k}", s0, s1, 0, z0, off=rec)
            if rec:  # niche end caps: solid from wall face out to recess plane
                wallbox(f"wall-e{i:02d}-cap{k}l", s0 - 60, s0, 0, z0, off=0, t=rec + WT)
                wallbox(f"wall-e{i:02d}-cap{k}r", s1, s1 + 60, 0, z0, off=0, t=rec + WT)
            glz = f"glass-{o['id']}"
            # thin pane mid-wall, shrunk 3mm so no face is coplanar with jambs/header/parapet
            if horiz:
                gy = my + outward * (WT * 0.5)
                box(glz, s0 + 3, gy - 15, z0 + 3, s1 - 3, gy + 15, z1 - 3)
            else:
                gx = mx + outward * (WT * 0.5)
                box(glz, gx - 15, s0 + 3, z0 + 3, gx + 15, s1 - 3, z1 - 3)
        cursor = s1
    if hi + EXT - cursor > 1: wallbox(f"wall-e{i:02d}-seg{len(ops)}", cursor, hi + EXT, 0, CEIL)

# ---------- structural risk volumes (stage 1+): visible, never silent ----------
for r in M.get("risk_elements", []):
    box(r["id"], *r["box"])

# ---------- stage 2: MEP ----------
if STAGE >= 2:
    mep = M["mep"]
    f = mep["fcu"]
    ty = f.get("throw", [0, -1])[1]
    y0, y1 = (f["face_y"], f["face_y"] + f["depth"]) if ty > 0 else (f["face_y"] - f["depth"], f["face_y"])
    box("mep-fcu", f["x"][0], y0, f["z"][0], f["x"][1], y1, f["z"][1])
    for t in mep["trunking"]:
        b = t["box"]; box(t["id"], *b)
    c = mep["compressor"]["box"]; box("mep-compressor", *c)
    for s in mep["sockets"]:
        p = s["p"]; box(s["id"], p[0] - 40, p[1] - 40, p[2] - 60, p[0] + 40, p[1] + 40, p[2] + 60)

# ---------- stage 3: furnishing ----------
if STAGE >= 3:
    for fitem in M["furniture"]:
        b = fitem["box"]
        box(f"{fitem['id']}:{fitem['kind']}", *b)
    for citem in M["curtains"]:
        b = citem["box"]
        box(citem["id"], *b)

# colors
design = STAGE >= 3
for ob in bpy.data.objects:
    if ob.type != 'MESH': continue
    k = klass(ob.name)
    early, dsn, idc = pal(k)
    ob.color = (dsn if design and dsn else (early or dsn))
    ob["idcolor"] = list(idc)
    ob["klass"] = k

# ---------- cameras ----------
scene = bpy.context.scene
cams = []
for c in M["cameras"]:
    cd = bpy.data.cameras.new(c["id"])
    if c.get("ortho"):
        cd.type = 'ORTHO'; cd.ortho_scale = c["scale"]
    else:
        cd.sensor_fit = 'HORIZONTAL'
        cd.angle = math.radians(c["fov_deg"])
    cd.clip_start = 50; cd.clip_end = 60000
    co = bpy.data.objects.new(c["id"], cd)
    scene.collection.objects.link(co)
    eye, tgt = Vector(c["eye"]), Vector(c["target"])
    co.location = eye
    co.rotation_euler = (tgt - eye).to_track_quat('-Z', 'Y').to_euler()
    cams.append(co)

# ---------- introspection + ray tests ----------
deps = bpy.context.evaluated_depsgraph_get()
intro = {"stage": STAGE, "objects": {}, "probes": {}, "enclosure": None}
for ob in bpy.data.objects:
    if ob.type != 'MESH': continue
    bb = [ob.matrix_world @ Vector(v) for v in ob.bound_box]
    mn = [min(v[i] for v in bb) for i in range(3)]
    mx = [max(v[i] for v in bb) for i in range(3)]
    intro["objects"][ob.name] = {"min": [round(v, 1) for v in mn], "max": [round(v, 1) for v in mx],
                                 "klass": ob.get("klass", "?")}

def ray(orig, dirv):
    hit, loc, nrm, idx, ob, mtx = scene.ray_cast(deps, Vector(orig), Vector(dirv).normalized())
    return (hit, (loc - Vector(orig)).length if hit else None, ob.name if hit else None)

# wall probes at each solid edge midpoint
probes = {}
for i in range(n):
    a, b = POLY[i], POLY[(i + 1) % n]
    mx_, my_ = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    horiz = abs(a[1] - b[1]) < 1e-6
    nrm = (0, 1, 0) if horiz else (1, 0, 0)
    if inside((mx_ + nrm[0] * 5, my_ + nrm[1] * 5)):
        nrm = (-nrm[0], -nrm[1], 0)
    else:
        nrm = (nrm[0], nrm[1], 0)
    start = (mx_ - nrm[0] * 300, my_ - nrm[1] * 300, 1300)
    hit, dist, obn = ray(start, nrm)
    probes[f"edge{i:02d}"] = {"hit": hit, "dist": dist and round(dist, 1), "obj": obn}
# opening probes
for o in M["openings"]:
    cx = (o["span"][0] + o["span"][1]) / 2
    fy = o["face_y"]
    outward = (0, 1, 0) if not inside((cx, fy + 5)) else (0, -1, 0)
    z = 1000 if o["kind"] == "door" else 1700
    start = (cx, fy - outward[1] * 300, z)
    hit, dist, obn = ray(start, outward)
    probes[o["id"]] = {"hit": hit, "dist": dist and round(dist, 1), "obj": obn}
intro["probes"] = probes

if STAGE == 1:
    door = [o for o in M["openings"] if o["kind"] == "door"][0]
    pts = [(1500, 2500, 1300), (3300, 1200, 1300), (4700, 2500, 1300), (1300, 1300, 1300), (4800, 350, 1300)]
    pts = [p for p in pts if inside((p[0], p[1]))]
    esc = []
    total = 0
    for p in pts:
        for k in range(48):
            ang = k * math.pi * 2 / 48
            total += 1
            hit, dist, obn = ray(p, (math.cos(ang), math.sin(ang), 0))
            if not hit:
                # does it exit through the door span?
                dx, dy = math.cos(ang), math.sin(ang)
                okdoor = False
                if abs(dy) > 1e-6:
                    t = (door["face_y"] - p[1]) / dy
                    if t > 0:
                        xx = p[0] + dx * t
                        okdoor = door["span"][0] - 5 <= xx <= door["span"][1] + 5
                if not okdoor:
                    esc.append({"from": p, "ang_deg": round(math.degrees(ang), 1)})
        for dz in ((0, 0, 1), (0, 0, -1)):
            total += 1
            hit, dist, obn = ray(p, dz)
            if not hit: esc.append({"from": p, "dir": dz})
    intro["enclosure"] = {"rays": total, "unexplained_escapes": esc}

json.dump(intro, open(f"{OUT}/audits/introspect_stage{STAGE}.json", "w"), indent=1)

# ---------- render ----------
import os
rd = f"{OUT}/renders/stage{STAGE}"
os.makedirs(rd, exist_ok=True)
scene.render.engine = 'BLENDER_WORKBENCH'
scene.render.resolution_x, scene.render.resolution_y = 1280, 960
scene.view_settings.view_transform = 'Standard'   # literal colors: ID pass must be exact, no AgX
scene.view_settings.look = 'None'
sh = scene.display.shading
scene.display.render_aa = 'FXAA'
sh.light = 'STUDIO'; sh.color_type = 'OBJECT'
sh.show_object_outline = True
sh.show_shadows = False
ceil_ob = bpy.data.objects["ceiling"]
for co in cams:
    scene.camera = co
    ceil_ob.hide_render = bool(co.name == "cam-top")   # top view is an audit view: see the floor
    scene.render.filepath = f"{rd}/{co.name}-vis.png"
    bpy.ops.render.render(write_still=True)
# id pass
scene.display.render_aa = 'OFF'
sh.light = 'FLAT'
sh.show_object_outline = False
for ob in bpy.data.objects:
    if ob.type == 'MESH':
        ob.color = tuple(ob["idcolor"])
for co in cams:
    scene.camera = co
    ceil_ob.hide_render = bool(co.name == "cam-top")
    scene.render.filepath = f"{rd}/{co.name}-id.png"
    bpy.ops.render.render(write_still=True)
ceil_ob.hide_render = False
# restore visual colors and save blend
for ob in bpy.data.objects:
    if ob.type == 'MESH':
        k = ob["klass"]
        early, dsn, idc = pal(k)
        ob.color = (dsn if design and dsn else (early or dsn))
bpy.ops.wm.save_as_mainfile(filepath=f"{OUT}/blend/stage{STAGE}.blend")
print(f"STAGE {STAGE} BUILD OK — {len([o for o in bpy.data.objects if o.type=='MESH'])} meshes")
