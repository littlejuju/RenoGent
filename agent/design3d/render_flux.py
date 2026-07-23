#!/usr/bin/env python3
"""Alternative stage-4b engine: flux-dev img2img at LOW prompt_strength.

Structure fidelity comes from the mechanism (only ~half the denoising budget can
move pixels away from the audited Cycles base) instead of prompt begging —
for camera views where nano-banana keeps hallucinating layout.

Usage: python3 render_flux.py <src.png> <dst.png> <prompt> [strength]
"""
import base64, json, os, pathlib, sys, time, urllib.request

API = "https://api.replicate.com/v1/models/black-forest-labs/flux-dev/predictions"

def token():
    if os.environ.get("REPLICATE_API_TOKEN"):
        return os.environ["REPLICATE_API_TOKEN"]
    return pathlib.Path.home().joinpath("Documents/credentials/replicate_api_token.txt").read_text().strip()

def run(src, dst, prompt, strength=0.5):
    uri = "data:image/png;base64," + base64.b64encode(pathlib.Path(src).read_bytes()).decode()
    body = json.dumps({"input": {
        "prompt": prompt, "image": uri, "prompt_strength": float(strength),
        "guidance": 3.5, "num_inference_steps": 40, "output_format": "png",
        "aspect_ratio": "4:3",
    }}).encode()
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "Authorization": f"Bearer {token()}", "Content-Type": "application/json", "Prefer": "wait=60"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        pred = json.load(r)
    while pred["status"] not in ("succeeded", "failed", "canceled"):
        time.sleep(2)
        q = urllib.request.Request(pred["urls"]["get"], headers={"Authorization": f"Bearer {token()}"})
        with urllib.request.urlopen(q, timeout=60) as r:
            pred = json.load(r)
    if pred["status"] != "succeeded":
        raise RuntimeError(f"flux failed: {pred.get('error')}")
    out = pred["output"][0] if isinstance(pred["output"], list) else pred["output"]
    urllib.request.urlretrieve(out, dst)
    print(f"flux OK ({time.time() - t0:.1f}s, strength={strength}) -> {dst}")

if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]) if len(sys.argv) > 4 else 0.5)
