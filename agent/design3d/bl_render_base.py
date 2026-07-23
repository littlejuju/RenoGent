# Stage 4a — photoreal base renders from the audited stage-3 scene.
# Run: Blender --background <stage3.blend> --python bl_render_base.py -- <room_model.json> <out_root>
# Cycles, P1 palette materials, sun through north windows, floor lamp is the only luminaire.
import bpy, sys, math
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
MODEL, OUT = argv[0], argv[1]
import json, os
M = json.load(open(MODEL))

MAT = {  # class -> (rgb, rough, extras)
    "wall":    ((0.93, 0.90, 0.84), 0.85, {}),
    "floor":   ((0.23, 0.13, 0.08), 0.45, {}),
    "ceiling": ((0.96, 0.95, 0.93), 0.9, {}),
    "glass":   ((0.9, 0.95, 1.0), 0.05, {"transmission": 1.0, "ior": 1.05, "alpha": 0.15}),
    "mep":     ((0.88, 0.88, 0.86), 0.6, {}),
    "closet":  ((0.62, 0.44, 0.28), 0.55, {}),
    "cabinet": ((0.90, 0.87, 0.80), 0.5, {}),
    "bed":     ((0.88, 0.85, 0.78), 0.95, {}),
    "table":   ((0.62, 0.44, 0.28), 0.5, {}),
    "lamp":    ((0.72, 0.58, 0.30), 0.35, {"emission": (1.0, 0.75, 0.45), "emission_strength": 3.0}),
    "rug":     ((0.90, 0.88, 0.82), 1.0, {}),
    "blackout":((0.72, 0.60, 0.48), 0.95, {}),
    "sheer":   ((0.96, 0.96, 0.94), 0.9, {"alpha": 0.35}),
}

mats = {}
for k, (rgb, rough, ex) in MAT.items():
    m = bpy.data.materials.new(f"m-{k}")
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1)
    bsdf.inputs["Roughness"].default_value = rough
    if "transmission" in ex:
        for nm in ("Transmission Weight", "Transmission"):
            if nm in bsdf.inputs: bsdf.inputs[nm].default_value = ex["transmission"]
        bsdf.inputs["IOR"].default_value = ex.get("ior", 1.45)
    if "alpha" in ex:
        bsdf.inputs["Alpha"].default_value = ex["alpha"]
        m.blend_method = 'BLEND' if hasattr(m, "blend_method") else m.blend_method
    if "emission" in ex:
        for nm in ("Emission Color", "Emission"):
            if nm in bsdf.inputs: bsdf.inputs[nm].default_value = (*ex["emission"], 1)
        bsdf.inputs["Emission Strength"].default_value = ex["emission_strength"]
    mats[k] = m

for ob in bpy.data.objects:
    if ob.type != 'MESH': continue
    k = ob.get("klass", "wall")
    ob.data.materials.clear()
    ob.data.materials.append(mats.get(k, mats["wall"]))

# --- lights: sun from the north (through both windows), warm fill from lamp only
# foyer backdrop: the door leads to an interior hallway, not open sky
door = [o for o in M["openings"] if o["kind"] == "door"][0]
fb = bpy.data.meshes.new("foyer-backdrop")
x0, x1 = door["span"][0] - 1200, door["span"][1] + 1200
fy = door["face_y"] - 900
fb.from_pydata([Vector((x0, fy, -100)), Vector((x1, fy, -100)), Vector((x1, fy, 2800)), Vector((x0, fy, 2800))],
               [], [(0, 1, 2, 3)])
fb.update()
fob = bpy.data.objects.new("foyer-backdrop", fb)
bpy.context.scene.collection.objects.link(fob)
fm = bpy.data.materials.new("m-foyer")
fm.use_nodes = True
fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.35, 0.32, 0.28, 1)
fob.data.materials.append(fm)

sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", 'SUN'))
bpy.context.scene.collection.objects.link(sun)
sun.data.energy = 6.0
sun.data.angle = math.radians(5)
d = Vector((-0.25, -1.0, -0.55)).normalized()      # from north sky down into the room
sun.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

w = bpy.context.scene.world or bpy.data.worlds.new("w")
bpy.context.scene.world = w
w.use_nodes = True
bg = w.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.75, 0.82, 0.92, 1)  # overcast sky
bg.inputs[1].default_value = 1.2

sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.cycles.samples = 160
sc.cycles.use_denoising = True
try:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'METAL'
    prefs.get_devices()
    for dev in prefs.devices: dev.use = True
    sc.cycles.device = 'GPU'
except Exception as e:
    print("METAL unavailable, CPU:", e)
sc.render.resolution_x, sc.render.resolution_y = 1280, 960
sc.view_settings.view_transform = 'AgX'
sc.view_settings.look = 'AgX - Base Contrast'

rd = f"{OUT}/renders/stage4-base"
os.makedirs(rd, exist_ok=True)
for cid in ("cam-entry", "cam-ne", "cam-br3"):
    sc.camera = bpy.data.objects[cid]
    sc.render.filepath = f"{rd}/{cid}-base.png"
    bpy.ops.render.render(write_still=True)
print("STAGE4 BASE RENDERS OK")
