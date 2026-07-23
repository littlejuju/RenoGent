"""Structure-freeze pixel diff between two deterministic Workbench renders.

new-layer mask comes from the ID pass of the later stage (class colors),
dilated; any changed pixel OUTSIDE the mask is a structure violation.
"""
import numpy as np
from PIL import Image

def srgb(v):
    return v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055

def class_mask(id_png, colors, tol=28):
    arr = np.asarray(Image.open(id_png).convert("RGB")).astype(int)
    m = np.zeros(arr.shape[:2], bool)
    for rgb in colors:
        t = np.array([round(srgb(v) * 255) for v in rgb])
        m |= (np.abs(arr - t).max(axis=2) < tol)
    return m

def dilate(m, it=6):
    for _ in range(it):
        m = (m | np.roll(m, 1, 0) | np.roll(m, -1, 0) | np.roll(m, 1, 1) | np.roll(m, -1, 1))
    return m

def classify(id_png, class_colors, tol=28):
    """Map each pixel to a class name via the ID palette; unmatched -> 'other'."""
    arr = np.asarray(Image.open(id_png).convert("RGB")).astype(int)
    out = np.full(arr.shape[:2], -1, np.int16)
    names = list(class_colors)
    for k, name in enumerate(names):
        t = np.array([round(srgb(v) * 255) for v in class_colors[name]])
        out[(np.abs(arr - t).max(axis=2) < tol) & (out == -1)] = k
    return out, names

def id_transition_diff(id_a, id_b, class_colors, structure, additive, out_png=None):
    """Palette-independent structure freeze: a structure-class pixel in A may stay
    the same class or be occluded by an additive class in B — anything else
    (structure->different structure, structure->background) is a violation."""
    ca, names = classify(id_a, class_colors)
    cb, _ = classify(id_b, class_colors)
    sidx = {names.index(s) for s in structure if s in names}
    aidx = {names.index(s) for s in additive if s in names}
    viol = np.zeros(ca.shape, bool)
    for s in sidx:
        m = ca == s
        ok = (cb == s) | np.isin(cb, list(aidx))
        viol |= m & ~ok
    if out_png is not None:
        dbg = np.zeros((*viol.shape, 3), np.uint8)
        dbg[np.isin(ca, list(sidx))] = (50, 50, 50)
        dbg[np.isin(cb, list(aidx))] = (30, 90, 30)
        dbg[viol] = (255, 40, 40)
        Image.fromarray(dbg).save(out_png)
    return {"violation_px": int(viol.sum()), "violation_pct": round(100 * viol.sum() / viol.size, 4)}

def freeze_diff(vis_a, vis_b, id_b, new_colors, out_png=None, delta_thresh=8):
    a = np.asarray(Image.open(vis_a).convert("RGB")).astype(int)
    b = np.asarray(Image.open(vis_b).convert("RGB")).astype(int)
    changed = np.abs(a - b).max(axis=2) > delta_thresh
    mask = dilate(class_mask(id_b, new_colors))
    viol = changed & ~mask
    if out_png is not None:
        dbg = np.zeros((*viol.shape, 3), np.uint8)
        dbg[changed] = (60, 60, 60); dbg[mask] = (30, 90, 30); dbg[viol] = (255, 40, 40)
        Image.fromarray(dbg).save(out_png)
    return {"changed_px": int(changed.sum()), "masked_px": int(mask.sum()),
            "violation_px": int(viol.sum()), "violation_pct": round(100 * viol.sum() / viol.size, 4)}
