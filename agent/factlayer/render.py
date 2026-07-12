#!/usr/bin/env python3
"""Structure-locked interior render (locked recipe: google/nano-banana on Replicate).

The room's geometry is part of the fact layer: the prompt pins walls, windows,
grilles, false ceiling and camera so the render cannot invent a different room.
~11s / $0.04 per image.

Usage: python3 render.py <input.jpg> <output.png> [style words]
Token: $REPLICATE_API_TOKEN or ~/Documents/credentials/replicate_api_token.txt
"""
import base64, json, os, pathlib, sys, time, urllib.request

API = "https://api.replicate.com/v1/models/google/nano-banana/predictions"

STRUCTURE_LOCK = (
    "Keep the exact same room geometry: same walls, same windows, same window "
    "grilles, same false ceiling shape, same camera angle. "
)
# Domain prior — Singapore HDB window typology. The image model's aesthetic
# default is floor-to-ceiling glass, which does not exist in HDB flats.
HDB_TYPOLOGY = (
    "This is a Singapore HDB flat. STRICT constraints: windows are standard HDB "
    "windows with a solid wall parapet below (sill about 1 metre above floor), "
    "top-hung casement or sliding panels with dark aluminium frames, arranged as "
    "a horizontal band. ABSOLUTELY NO floor-to-ceiling windows, NO curtain walls, "
    "NO balcony unless the floor plan shows one. Ceiling is flat concrete about "
    "2.6m high; false ceiling only as a perimeter L-box. "
)
DEFAULT_STYLE = (
    "Renovate this room into a warm japandi style: matte oak wood flooring, "
    "warm cove lighting, linen curtains, tasteful furniture, realistic materials, "
    "photorealistic professional interior photography."
)


def token():
    if os.environ.get("REPLICATE_API_TOKEN"):
        return os.environ["REPLICATE_API_TOKEN"]
    return pathlib.Path.home().joinpath(
        "Documents/credentials/replicate_api_token.txt").read_text().strip()


def preprocess(src: str) -> str:
    """Auto-crop phone-screenshot chrome: keep the white document/photo region.
    Part of the locked recipe — nano-banana refuses screenshots with UI frames."""
    try:
        from PIL import Image
    except ImportError:
        return src
    im = Image.open(src).convert("RGB")
    w, h = im.size
    px = im.convert("L").point(lambda p: 1 if p > 200 else 0).load()
    # density scan: the document is the block of rows/cols that are mostly white;
    # a global bbox fails because isolated white UI icons (battery, clock) extend it
    rows = [y for y in range(h) if sum(px[x, y] for x in range(0, w, 4)) * 4 > 0.5 * w]
    if not rows:
        return src
    y0, y1 = rows[0], rows[-1]
    cols = [x for x in range(w) if sum(px[x, y] for y in range(y0, y1, 4)) * 4 > 0.5 * (y1 - y0)]
    if not cols:
        return src
    x0, x1 = cols[0], cols[-1]
    if (x1 - x0) * (y1 - y0) > 0.95 * w * h or (x1 - x0) * (y1 - y0) < 0.20 * w * h:
        return src
    pad = 8
    crop = im.crop((max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad)))
    out = src.rsplit(".", 1)[0] + "-cropped.jpg"
    crop.save(out, "JPEG", quality=92)
    print(f"preprocess: cropped {im.size} -> {crop.size}")
    return out


def render(src: str, dst: str, style: str = DEFAULT_STYLE, edit_instruction: str = "", attempts: int = 3):
    src = preprocess(src)
    uri = "data:image/jpeg;base64," + base64.b64encode(pathlib.Path(src).read_bytes()).decode()
    prompt = (edit_instruction + " " if edit_instruction else "") + STRUCTURE_LOCK + HDB_TYPOLOGY + style
    # nano-banana refuses doc-style inputs nondeterministically; the explicit
    # plan-mode phrasing recovers most refusals, so later attempts switch to it
    plan_prompt = ("This image is a 2D architectural floor plan of a Singapore HDB flat. "
                   "Generate a photorealistic interior render of the LIVING/DINING room only, "
                   "camera standing at the internal corridor entrance looking toward the "
                   "living/dining exterior wall (the wall with the window band and the "
                   "2800mm-wide opening shown in the plan). Respect the plan's wall, window "
                   "and door positions exactly. " + HDB_TYPOLOGY) + (edit_instruction or style)
    last = None
    for i in range(attempts):
        try:
            return _render_once(uri, dst, prompt if i < 1 else plan_prompt)
        except (RuntimeError, urllib.error.HTTPError) as e:
            last = e
            wait = 12 if (isinstance(e, urllib.error.HTTPError) and e.code == 429) else 3
            print(f"attempt {i+1}/{attempts} failed: {e} (retry in {wait}s)")
            time.sleep(wait)
    raise last


def _render_once(uri: str, dst: str, prompt: str):
    req = urllib.request.Request(
        API,
        data=json.dumps({"input": {"image_input": [uri], "prompt": prompt}}).encode(),
        headers={"Authorization": f"Bearer {token()}",
                 "Content-Type": "application/json", "Prefer": "wait=60"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        pred = json.load(r)
    while pred["status"] in ("starting", "processing"):
        time.sleep(3)
        q = urllib.request.Request(f"https://api.replicate.com/v1/predictions/{pred['id']}",
                                   headers={"Authorization": f"Bearer {token()}"})
        with urllib.request.urlopen(q, timeout=60) as r:
            pred = json.load(r)
    if pred["status"] != "succeeded":
        raise RuntimeError(f"render failed: {str(pred.get('error'))[:300]}")
    out = pred["output"]
    urllib.request.urlretrieve(out if isinstance(out, str) else out[0], dst)
    print(f"render OK ({time.time()-t0:.1f}s) -> {dst}")


if __name__ == "__main__":
    render(sys.argv[1], sys.argv[2], " ".join(sys.argv[3:]) or DEFAULT_STYLE)
