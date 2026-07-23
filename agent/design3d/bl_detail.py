# Stage 4a-detail — decorate the AUDITED stage-3 scene in place (route 1: rich Blender base,
# generative pass becomes optional polish). Substrate geometry is untouched: decorations are
# skins/props within existing audited volumes, so gates A0-A3 remain valid.
# Run: Blender --background <stage3.blend> --python bl_detail.py -- <room_model.json> <out_root>
import bpy, json, math, os, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
M = json.load(open(argv[0])); OUT = argv[1]
CEIL = M["ceiling_mm"]
S = bpy.context.scene

# ---------------- materials ----------------
def new_mat(name):
    m = bpy.data.materials.new(name); m.use_nodes = True
    return m, m.node_tree, m.node_tree.nodes["Principled BSDF"]

def wood(name, light, dark, scale=0.0008, rot=0.0, rough=0.45):
    m, nt, b = new_mat(name)
    tc = nt.nodes.new("ShaderNodeTexCoord"); mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (0, 0, rot)
    mp.inputs["Scale"].default_value = (scale * 900, scale * 14000, scale * 900)
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.inputs["Scale"].default_value = 1.2; wv.inputs["Distortion"].default_value = 6
    wv.inputs["Detail"].default_value = 3
    no = nt.nodes.new("ShaderNodeTexNoise"); no.inputs["Scale"].default_value = 9
    mixf = nt.nodes.new("ShaderNodeMix"); mixf.data_type = 'FLOAT'
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].color = (*light, 1); cr.color_ramp.elements[1].color = (*dark, 1)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], wv.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], no.inputs["Vector"])
    nt.links.new(wv.outputs["Fac"], mixf.inputs[2]); nt.links.new(no.outputs["Fac"], mixf.inputs[3])
    mixf.inputs[0].default_value = 0.35
    nt.links.new(mixf.outputs[0], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = rough
    return m

def floor_mat():
    m, nt, b = new_mat("d-floor")
    tc = nt.nodes.new("ShaderNodeTexCoord"); mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / 1400, 1 / 190, 1)   # plank 1400x190mm
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.offset = 0.5; br.inputs["Mortar Size"].default_value = 0.006
    br.inputs["Color1"].default_value = (0.16, 0.085, 0.05, 1)
    br.inputs["Color2"].default_value = (0.21, 0.115, 0.065, 1)
    br.inputs["Mortar"].default_value = (0.06, 0.035, 0.025, 1)
    br.inputs["Scale"].default_value = 1.0
    wv = nt.nodes.new("ShaderNodeTexWave"); wv.inputs["Scale"].default_value = 0.4
    wv.inputs["Distortion"].default_value = 8
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = 'RGBA'; mix.inputs[0].default_value = 0.18
    mix.inputs[7].default_value = (0.10, 0.05, 0.03, 1)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], br.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], wv.inputs["Vector"])
    nt.links.new(br.outputs["Color"], mix.inputs[6])
    nt.links.new(wv.outputs["Fac"], mix.inputs[0])
    nt.links.new(mix.outputs[2], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.35
    return m

def plain(name, rgb, rough=0.85, metal=0.0, alpha=1.0, emis=None, estr=0.0):
    m, nt, b = new_mat(name)
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if alpha < 1: b.inputs["Alpha"].default_value = alpha
    if emis:
        for nm in ("Emission Color", "Emission"):
            if nm in b.inputs: b.inputs[nm].default_value = (*emis, 1)
        b.inputs["Emission Strength"].default_value = estr
    return m

def glass_mat():
    m, nt, b = new_mat("d-glass")
    b.inputs["Base Color"].default_value = (0.92, 0.96, 1, 1)
    b.inputs["Roughness"].default_value = 0.03
    for nm in ("Transmission Weight", "Transmission"):
        if nm in b.inputs: b.inputs[nm].default_value = 1.0
    b.inputs["IOR"].default_value = 1.05
    return m

MATS = {
    "floor": floor_mat(),
    "walnut-light": wood("d-oak", (0.72, 0.56, 0.38), (0.55, 0.40, 0.25), rot=math.pi / 2, rough=0.5),
    "wall": plain("d-wall", (0.91, 0.88, 0.82), 0.9),
    "ceiling": plain("d-ceil", (0.95, 0.94, 0.92), 0.92),
    "linen": plain("d-linen", (0.90, 0.87, 0.80), 0.97),
    "linen-white": plain("d-linen-w", (0.93, 0.91, 0.86), 0.97),
    "offwhite-cab": plain("d-cab", (0.90, 0.87, 0.80), 0.55),
    "blackout": plain("d-blackout", (0.62, 0.50, 0.39), 0.95),
    "sheer": plain("d-sheer", (0.96, 0.96, 0.94), 0.9, alpha=0.32),
    "brass": plain("d-brass", (0.75, 0.58, 0.28), 0.3, metal=1.0),
    "white-plastic": plain("d-fcu", (0.94, 0.94, 0.93), 0.4),
    "alu": plain("d-alu", (0.15, 0.15, 0.16), 0.4, metal=0.8),
    "shade": plain("d-shade", (0.95, 0.88, 0.75), 0.6, emis=(1.0, 0.75, 0.45), estr=14),
    "rug": plain("d-rug", (0.88, 0.86, 0.80), 1.0),
    "glass": glass_mat(),
    "foyer": plain("d-foyer", (0.45, 0.41, 0.36), 0.9),
    "grey": plain("d-grey", (0.75, 0.75, 0.74), 0.7),
}

def assign(ob, mat):
    ob.data.materials.clear(); ob.data.materials.append(mat)

def mkbox(name, x0, y0, z0, x1, y1, z1, mat):
    me = bpy.data.meshes.new(name)
    v = [(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
    f = [(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
    me.from_pydata([Vector(p) for p in v], [], f); me.update()
    ob = bpy.data.objects.new(name, me); S.collection.objects.link(ob)
    assign(ob, mat)
    return ob

def bevel(ob, w=40, seg=3):
    b = ob.modifiers.new("bv", 'BEVEL'); b.width = w; b.segments = seg; b.angle_limit = math.radians(50)

# ---------------- re-skin audited objects ----------------
objs = {o.name: o for o in bpy.data.objects if o.type == 'MESH'}
def bb(o):
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return ([min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)])

for name, o in objs.items():
    k = o.get("klass", "")
    if name == "floor": assign(o, MATS["floor"])
    elif name == "ceiling": assign(o, MATS["ceiling"])
    elif name.startswith("wall"): assign(o, MATS["wall"])
    elif name.startswith("glass"): assign(o, MATS["glass"])
    elif k == "closet" or k == "table": assign(o, MATS["walnut-light"])
    elif k == "cabinet": assign(o, MATS["offwhite-cab"])
    elif k == "rug": assign(o, MATS["rug"])
    elif k == "bed": assign(o, MATS["walnut-light"])
    elif name.startswith("mep") or name.startswith("skt"): assign(o, MATS["white-plastic"])
    elif name.startswith("risk"): assign(o, MATS["ceiling"])   # design renders: boxed bulkhead look (beam-present basis)

# door gaps + handles on joinery fronts: (object, front axis, sign, n_doors, handle)
JOINERY = [
    ("fur-closet-west:closet", 0, +1, 2, True), ("fur-closet-south:closet", 1, +1, 3, True),
    ("fur-closet-return:closet", 0, +1, 0, False), ("fur-wardrobe-pocket:closet", 1, +1, 3, True),
    ("fur-cab-bay:closet", 1, -1, 2, True),
    ("fur-cab-br3:cabinet", 1, -1, 4, False), ("fur-cab-br1:cabinet", 1, -1, 3, False),
    ("fur-nightstand-n:table", 0, -1, 0, False), ("fur-nightstand-s:table", 0, -1, 0, False),
]
GAP, PROUD = 7, 3
for name, ax, sign, ndoors, handle in JOINERY:
    o = objs.get(name)
    if not o: continue
    mn, mx = bb(o)
    face = (mx if sign > 0 else mn)[ax] + sign * PROUD
    u = 1 - ax  # horizontal axis along the front (0 or 1)
    lo, hi = mn[u], mx[u]
    zt = mx[2]
    mat_gap = plain(f"gap-{name}", (0.05, 0.04, 0.03), 0.9)
    for d in range(1, max(ndoors, 1)):
        p = lo + (hi - lo) * d / ndoors
        co = [0, 0, 0, 0, 0, 0]
        co[ax], co[ax + 3] = face - sign * 6, face
        co[u], co[u + 3] = p - GAP / 2, p + GAP / 2
        co[2], co[5] = mn[2] + 20, zt - 20
        mkbox(f"gap-{name}-{d}", *co, mat_gap)
    if handle and ndoors:
        for d in range(ndoors):
            p = lo + (hi - lo) * (d + (0.88 if d % 2 == 0 else 0.12)) / ndoors
            co = [0, 0, 0, 0, 0, 0]
            co[ax], co[ax + 3] = face, face + sign * 18
            co[u], co[u + 3] = p - 10, p + 10
            zc = min(1100, zt - 300)
            co[2], co[5] = zc - 150, zc + 150
            mkbox(f"hdl-{name}-{d}", *co, MATS["brass"])
    if name.startswith("fur-cab-") and "bay" not in name:
        mn2, mx2 = bb(o)   # counter top slab on low cabinets
        mkbox(f"top-{name}", mn2[0] - 15, mn2[1] - 15 * sign if ax == 1 else mn2[1], mx2[2],
              mx2[0] + 15, mx2[1], mx2[2] + 22, MATS["walnut-light"])

# bed dressing: frame stays walnut; add mattress, duvet, pillows
bed = objs.get("fur-bed:bed")
if bed:
    mn, mx = bb(bed)
    mat = mkbox("bed-mattress", mn[0] + 40, mn[1] + 40, mx[2] - 60, mx[0] - 120, mx[1] - 40, mx[2] + 160, MATS["linen-white"]); bevel(mat, 60)
    duv = mkbox("bed-duvet", mn[0] + 10, mn[1] + 10, mx[2] + 120, mx[0] - 700, mx[1] - 10, mx[2] + 300, MATS["linen"]); bevel(duv, 90, 4)
    for i, yc in enumerate((mn[1] + 480, mx[1] - 480)):
        # NOTE: no object-level rotation — mesh verts are absolute world coords with the
        # object at origin, so any rotation orbits the world origin and flings the prop away
        pw = mkbox(f"bed-pillow-{i}", mx[0] - 620, yc - 330, mx[2] + 150, mx[0] - 140, yc + 330, mx[2] + 340, MATS["linen-white"])
        bevel(pw, 110, 4)

# curtains -> wave strips
def wave_curtain(name, x0, x1, ymid, z0, z1, mat, amp=26, period=140):
    n = max(8, int((x1 - x0) / 45))
    vs, fs = [], []
    for i in range(n + 1):
        x = x0 + (x1 - x0) * i / n
        y = ymid + amp * math.sin(2 * math.pi * x / period)
        vs += [(x, y, z0), (x, y, z1)]
        if i: fs.append((2 * i - 2, 2 * i, 2 * i + 1, 2 * i - 1))
    me = bpy.data.meshes.new(name); me.from_pydata([Vector(v) for v in vs], [], fs); me.update()
    ob = bpy.data.objects.new(name, me); S.collection.objects.link(ob); assign(ob, mat)
    sol = ob.modifiers.new("s", 'SOLIDIFY'); sol.thickness = 8
    return ob

for c in M["curtains"]:
    o = objs.get(c["id"])
    if o: bpy.data.objects.remove(o, do_unlink=True)
    b = c["box"]
    mat = MATS["blackout"] if c["layer"] == "blackout" else MATS["sheer"]
    wave_curtain(c["id"] + "-w", min(b[0], b[3]), max(b[0], b[3]), (b[1] + b[4]) / 2, b[2], b[5], mat,
                 amp=22 if c["layer"] == "sheer" else 30)

# window frames + mullions at each glass pane
for gname in ("glass-win-br1", "glass-win-br3"):
    g = objs.get(gname)
    if not g: continue
    mn, mx = bb(g)
    yc0, yc1 = mn[1] - 22, mx[1] + 22
    FR = 45
    mkbox(f"frame-{gname}-b", mn[0], yc0, mn[2] - 10, mx[0], yc1, mn[2] + FR, MATS["alu"])
    mkbox(f"frame-{gname}-t", mn[0], yc0, mx[2] - FR, mx[0], yc1, mx[2] + 10, MATS["alu"])
    mkbox(f"frame-{gname}-l", mn[0] - 5, yc0, mn[2], mn[0] + FR, yc1, mx[2], MATS["alu"])
    mkbox(f"frame-{gname}-r", mx[0] - FR, yc0, mx[0] + 5, yc1, mx[2], mx[2], MATS["alu"]) if False else \
        mkbox(f"frame-{gname}-r2", mx[0] - FR, yc0, mn[2], mx[0] + 5, yc1, mx[2], MATS["alu"])
    span = mx[0] - mn[0]
    nmul = max(1, round(span / 700) - 1)
    for i in range(1, nmul + 1):
        xm = mn[0] + span * i / (nmul + 1)
        mkbox(f"mull-{gname}-{i}", xm - 22, yc0, mn[2], xm + 22, yc1, mx[2], MATS["alu"])
    # horizontal transom at 2/3 height (top-hung casement line)
    zt = mn[2] + (mx[2] - mn[2]) * 0.62
    mkbox(f"trans-{gname}", mn[0], yc0, zt - 20, mx[0], yc1, zt + 20, MATS["alu"])

# FCU vent groove on the throw-side face
f = objs.get("mep-fcu")
if f:
    mn, mx = bb(f)
    ty = M["mep"]["fcu"].get("throw", [0, -1])[1]
    vy0, vy1 = (mx[1] - 10, mx[1] + 4) if ty > 0 else (mn[1] - 4, mn[1] + 10)
    mkbox("fcu-vent", mn[0] + 40, vy0, mn[2] + 30, mx[0] - 40, vy1, mn[2] + 80, plain("vent", (0.2, 0.2, 0.2), 0.6))
    bevel(f, 25, 2)

# floor lamp -> pole + shade
lamp = objs.get("fur-lamp:lamp")
if lamp:
    mn, mx = bb(lamp)
    cx, cy = (mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2
    bpy.data.objects.remove(lamp, do_unlink=True)
    bpy.ops.mesh.primitive_cylinder_add(radius=14, depth=1350, location=(cx, cy, 675))
    pole = bpy.context.active_object; pole.name = "lamp-pole"; assign(pole, MATS["brass"])
    bpy.ops.mesh.primitive_cylinder_add(radius=170, depth=230, location=(cx, cy, 1360))
    sh = bpy.context.active_object; sh.name = "lamp-shade"; assign(sh, MATS["shade"])
    bpy.ops.mesh.primitive_cylinder_add(radius=140, depth=18, location=(cx, cy, 9))
    base = bpy.context.active_object; base.name = "lamp-base"; assign(base, MATS["brass"])

# foyer backdrop + door leaf (open 60deg) for realism outside the door
door = [o for o in M["openings"] if o["kind"] == "door"][0]
mkbox("foyer-wall", door["span"][0] - 1500, door["face_y"] - 950, -100,
      door["span"][1] + 1500, door["face_y"] - 900, 2800, MATS["foyer"])
mkbox("foyer-floor", door["span"][0] - 1500, door["face_y"] - 950, -100,
      door["span"][1] + 1500, door["face_y"], 0, MATS["grey"])

# ---------------- light & render ----------------
for l in [o for o in bpy.data.objects if o.type == 'LIGHT']:
    bpy.data.objects.remove(l, do_unlink=True)
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", 'SUN'))
S.collection.objects.link(sun)
sun.data.energy = 5.5; sun.data.angle = math.radians(2)
d = Vector((-0.18, -1.0, -0.5)).normalized()
sun.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

w = S.world or bpy.data.worlds.new("w"); S.world = w
w.use_nodes = True
nt = w.node_tree
for n in list(nt.nodes): nt.nodes.remove(n)
sky = nt.nodes.new("ShaderNodeTexSky")
try:
    sky.sky_type = 'NISHITA'; sky.sun_elevation = math.radians(38); sky.sun_rotation = math.radians(200)
    sky.sun_intensity = 0.35
except Exception: pass
bg = nt.nodes.new("ShaderNodeBackground"); out = nt.nodes.new("ShaderNodeOutputWorld")
bg.inputs[1].default_value = 0.35
nt.links.new(sky.outputs[0], bg.inputs[0]); nt.links.new(bg.outputs[0], out.inputs[0])

S.render.engine = 'CYCLES'
S.cycles.samples = 320; S.cycles.use_denoising = True
try:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'METAL'; prefs.get_devices()
    for dev in prefs.devices: dev.use = True
    S.cycles.device = 'GPU'
except Exception as e:
    print("METAL unavailable:", e)
S.render.resolution_x, S.render.resolution_y = 1280, 960
S.view_settings.view_transform = 'AgX'; S.view_settings.look = 'AgX - Base Contrast'

rd = f"{OUT}/renders/stage4-detail"
os.makedirs(rd, exist_ok=True)
for cid in [c["id"] for c in M["cameras"] if not c.get("ortho")]:
    S.camera = bpy.data.objects[cid]
    S.render.filepath = f"{rd}/{cid}-detail.png"
    bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=f"{OUT}/blend/stage4-detail.blend")
print("STAGE4 DETAIL RENDERS OK")
