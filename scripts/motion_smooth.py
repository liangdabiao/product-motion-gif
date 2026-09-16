"""motion_smooth.py - quantify frame-to-frame smoothness.

Two jitter sources are separable and it matters which one you are looking at:

  * the frame sheet itself   -> the model sampled the poses unevenly
  * the compositor           -> the per-frame stabiliser shift introduced jitter

Both show up the same way to the eye. The numbers below tell them apart:

  step        first difference  - how far the subject moved between two frames
              a smooth take wants these to be *equal*, not merely small
  accel       second difference - change-of-change; this IS the jitter
  jitter_idx  rms(accel) / mean|step|
              ~0   -> perfectly even motion
              >0.5 -> visible stutter

Usage:
    python motion_smooth.py <sheet_or_frame_dir> [rows cols] [--bg auto]
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import giflab as G  # noqa: E402


def series_stats(v: np.ndarray) -> dict:
    v = np.asarray(v, dtype=float)
    if len(v) < 3:
        return {}
    step = np.diff(v)
    acc = np.diff(step)
    scale = float(np.abs(step).mean())
    rms = float(np.sqrt((acc ** 2).mean()))
    return {
        "step_mean": round(float(np.abs(step).mean()), 3),
        "step_cv": round(float(np.abs(step).std() / (scale + 1e-9)), 3),
        "step_max": round(float(np.abs(step).max()), 3),
        "step_max_at": int(np.argmax(np.abs(step)) + 2),
        "accel_rms": round(rms, 3),
        "jitter_idx": round(rms / (scale + 1e-9), 3),
    }


def load_any(path: str, rows: int = 4, cols: int = 4, bg: str = "auto") -> list[Image.Image]:
    if os.path.isdir(path):
        files = sorted(f for f in os.listdir(path)
                       if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")))
        return [Image.open(os.path.join(path, f)).convert("RGBA") for f in files]
    return G.slice_sheet(G.load_image(path), rows, cols)


def analyse(path: str, rows: int = 4, cols: int = 4, bg: str = "auto") -> dict:
    frames = load_any(path, rows, cols, bg)
    stats = G.measure(frames, bg)
    cx = np.array([s.cx for s in stats])
    cy = np.array([s.cy for s in stats])
    bx = np.array([s.bx for s in stats])
    by = np.array([s.by for s in stats])
    area = np.array([s.area for s in stats], dtype=float)

    # pose fingerprint distance: the right signal for rotations, where the centroid
    # barely moves but the silhouette changes a lot
    pose = np.array([float(np.linalg.norm(stats[i].desc - stats[i - 1].desc))
                     for i in range(1, len(stats))])

    out = {
        "source": path,
        "frames": len(frames),
        "centroid_x": series_stats(cx),
        "centroid_y": series_stats(cy),
        "bbox_x": series_stats(bx),
        "bbox_y": series_stats(by),
        "area": series_stats(area),
        "pose_step": [round(float(v), 3) for v in pose],
        "pose": series_stats(pose),
    }
    out["verdict"] = _verdict(out)
    return out


def _verdict(r: dict) -> str:
    p = r["pose"].get("jitter_idx", 0)
    c = max(r["centroid_x"].get("jitter_idx", 0), r["centroid_y"].get("jitter_idx", 0))
    worst = max(p, c)
    if worst < 0.35:
        return "SMOOTH"
    if worst < 0.7:
        return "MILD STUTTER"
    return "JITTERY"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = [a for a in sys.argv[1:] if a.startswith("--")]
    path = args[0]
    rows = int(args[1]) if len(args) > 1 else 4
    cols = int(args[2]) if len(args) > 2 else 4
    bg = "auto"
    for o in opts:
        if o.startswith("--bg="):
            bg = o.split("=", 1)[1]

    r = analyse(path, rows, cols, bg)
    print(f"\n=== {path}   ({r['frames']} frames)   [{r['verdict']}]")
    for k in ("centroid_x", "centroid_y", "bbox_x", "bbox_y", "area", "pose"):
        s = r[k]
        if not s:
            continue
        print(f"  {k:11s} step_mean={s['step_mean']:8.3f}  step_cv={s['step_cv']:6.3f}  "
              f"max_step={s['step_max']:8.3f}@f{s['step_max_at']:02d}  "
              f"jitter_idx={s['jitter_idx']:6.3f}")
    print("  pose step per frame:", " ".join(f"{v:.3f}" for v in r["pose_step"]))
    if len(opts) and "--json" in " ".join(opts):
        print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
