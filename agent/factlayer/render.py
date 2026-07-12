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


def render(src: str, dst: str, style: str = DEFAULT_STYLE, edit_instruction: str = ""):
    uri = "data:image/jpeg;base64," + base64.b64encode(pathlib.Path(src).read_bytes()).decode()
    prompt = (edit_instruction + " " if edit_instruction else "") + STRUCTURE_LOCK + style
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
