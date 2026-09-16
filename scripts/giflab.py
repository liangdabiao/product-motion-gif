"""giflab - turn a GPT-Image 2.5 frame sheet into a clean looping product GIF.

The interesting problems this module solves, in order of impact:

1.  **Grid slicing + one global crop.**  The model does not keep the subject at a
    fixed position inside each cell, so cropping cell-by-cell makes the animation
    jitter.  We crop every frame with the SAME bounding box (the union of all
    subject masks), which is jitter-free by construction.

2.  **Slow-drift stabilisation.**  Over 16 cells the subject often migrates a few
    percent of the frame (a translation the prompt never asked for).  We high-pass
    the subject trajectory: a wide moving average is treated as drift and removed,
    while genuine motion survives.

3.  **Loop repair.**  The last cell is almost never a continuation of the first.
    Depending on how the silhouette behaves we either mirror a half cycle
    (`halfloop`, seamless by construction) or cut the tail at the cell whose
    silhouette best matches cell 1 (`loopcut`).

4.  **One shared palette.**  Quantising each GIF frame with its own palette makes
    the colours flicker.  A single palette derived from a mosaic of all frames
    removes that.

Everything is plain Pillow + NumPy; ffmpeg is used only for the optional MP4.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

# --------------------------------------------------------------------------- io


def load_image(path: str) -> Image.Image:
    im = Image.open(path)
    if im.mode == "P":
        im = im.convert("RGBA")
    return im


def slice_sheet(sheet: Image.Image, rows: int = 4, cols: int = 4,
                row_order: str = "top-down") -> list[Image.Image]:
    """Cut a frame sheet into rows*cols cells, reading order left->right, top->bottom."""
    W, H = sheet.size
    cw, ch = W // cols, H // rows
    out = []
    rng = range(rows) if row_order == "top-down" else range(rows - 1, -1, -1)
    for r in rng:
        for c in range(cols):
            out.append(sheet.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))
                       .convert("RGBA"))
    return out


# ------------------------------------------------------------------- masking


def has_alpha(frames: list[Image.Image]) -> bool:
    for f in frames:
        if f.mode == "RGBA":
            a = np.asarray(f.getchannel("A"))
            if float((a < 250).mean()) > 0.05:
                return True
    return False


def bg_mask(im: Image.Image, bg: str = "auto", tol: float = 26.0) -> np.ndarray:
    """Boolean mask of 'subject' pixels.

    bg = "transparent" -> alpha is authoritative (use for --transparency sheets)
    bg = "auto"        -> background colour sampled from the four corners
    bg = "r,g,b"       -> explicit background colour
    """
    a = np.asarray(im.convert("RGBA"))
    alpha = a[..., 3]
    if bg == "transparent":
        return alpha > 24
    # float32 plus a per-channel accumulator.  The old form built a float64 (h, w, 3)
    # temporary - ~12 MiB for a single 4K cell - and sixteen of those back to back is
    # enough to OOM a machine that is already short on RAM.
    rgb = a[..., :3].astype(np.float32)
    if bg == "auto":
        h, w = rgb.shape[:2]
        corners = np.stack([rgb[0, 0], rgb[0, w - 1], rgb[h - 1, 0], rgb[h - 1, w - 1]])
        ref = corners.mean(axis=0)
    else:
        ref = np.array([float(c) for c in bg.split(",")], dtype=np.float32)
    dist2 = np.zeros(rgb.shape[:2], dtype=np.float32)
    for c in range(3):
        d = rgb[..., c] - ref[c]
        dist2 += d * d
    return (dist2 > tol * tol) & (alpha > 24)


def union_bbox(masks: list[np.ndarray], pad_ratio: float = 0.04) -> tuple[int, int, int, int]:
    """Single bounding box covering the subject in every frame."""
    ys, xs = [], []
    for m in masks:
        yy, xx = np.nonzero(m)
        if len(yy):
            ys += [yy.min(), yy.max()]
            xs += [xx.min(), xx.max()]
    if not ys:
        raise SystemExit("no subject pixels found - check --bg / --trim")
    h, w = masks[0].shape
    y0, y1, x0, x1 = min(ys), max(ys), min(xs), max(xs)
    pad = int(max(y1 - y0, x1 - x0) * pad_ratio)
    return (max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + 1 + pad), min(h, y1 + 1 + pad))


# ---------------------------------------------------------------- measurement


@dataclass
class FrameStat:
    cx: float
    cy: float
    area: int
    bx: float          # bbox centre x
    by: float          # bbox centre y
    w: int
    h: int
    desc: np.ndarray = field(repr=False, default=None)


def silhouette_desc(im: Image.Image, bg: str, n: int = 24) -> np.ndarray:
    """Small normalised silhouette thumbnail - a cheap 'pose fingerprint'."""
    m = bg_mask(im, bg)
    yy, xx = np.nonzero(m)
    if len(yy) == 0:
        return np.zeros((n, n), dtype=np.float32)
    crop = (m[yy.min():yy.max() + 1, xx.min():xx.max() + 1] * 255).astype(np.uint8)
    small = np.asarray(Image.fromarray(crop).resize((n, n), Image.BILINEAR),
                       dtype=np.float32) / 255.0
    nrm = np.linalg.norm(small)
    return small / nrm if nrm > 0 else small


def measure(frames: list[Image.Image], bg: str = "auto", with_desc: bool = True) -> list[FrameStat]:
    out = []
    for f in frames:
        m = bg_mask(f, bg)
        yy, xx = np.nonzero(m)
        if len(yy) == 0:
            out.append(FrameStat(0, 0, 0, 0, 0, 0, 0,
                                 silhouette_desc(f, bg) if with_desc else None))
            continue
        out.append(FrameStat(
            cx=float(xx.mean()), cy=float(yy.mean()), area=int(m.sum()),
            bx=float((xx.min() + xx.max()) / 2), by=float((yy.min() + yy.max()) / 2),
            w=int(xx.max() - xx.min() + 1), h=int(yy.max() - yy.min() + 1),
            desc=silhouette_desc(f, bg) if with_desc else None,
        ))
    return out


def area_cv(stats: list[FrameStat]) -> float:
    a = np.array([s.area for s in stats], dtype=float)
    return float(a.std() / a.mean()) if a.mean() else 0.0


def moving_trend(v: np.ndarray, window: int) -> np.ndarray:
    """Centred moving average, edge-padded."""
    window = max(3, min(window, len(v) if len(v) % 2 else len(v) - 1))
    if window % 2 == 0:
        window += 1
    window = min(window, len(v) if len(v) % 2 else len(v) - 1)
    if window < 3:
        return np.full_like(v, v.mean())
    half = window // 2
    pad = np.pad(v, half, mode="edge")
    return np.convolve(pad, np.ones(window) / window, mode="valid")


def classify(stats: list[FrameStat]) -> dict:
    """Decide what kind of motion the sheet encodes.

    Key insight: a *rigid translation* (float, pulse, sway) keeps the silhouette
    area almost constant, while a *pose change* (rotation, reveal, open/close)
    changes the projected area a lot.  That single number separates the two cases
    far more reliably than looking at the centroid alone.
    """
    cx = np.array([s.cx for s in stats])
    cy = np.array([s.cy for s in stats])
    cv = area_cv(stats)
    rx, ry = float(cx.max() - cx.min()), float(cy.max() - cy.min())
    if cv >= 0.05:
        kind = "pose-change"
    elif max(rx, ry) > 4:
        kind = "translation"
    else:
        kind = "static"
    return {"kind": kind, "area_cv": round(cv, 4),
            "cx_range": round(rx, 1), "cy_range": round(ry, 1),
            "axis": "y" if ry >= rx else "x"}


# --------------------------------------------------------------- stabilising


def flatten_rgb(im: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    """Composite an RGBA frame onto an opaque background.

    Dropping the alpha channel outright (``convert("RGB")``) sends fully transparent
    pixels to BLACK.  After stabilisation the frame edges are exactly that - the
    strip vacated by the shift - so a naive convert paints a dark border around
    every frame.  Compositing over the canvas colour instead keeps the border
    invisible, which is what a white-background sheet needs.
    """
    if im.mode != "RGBA":
        return im.convert("RGB")
    base = Image.new("RGBA", im.size, tuple(bg) + (255,))
    return Image.alpha_composite(base, im).convert("RGB")


def shift_frame(im: Image.Image, dx: float, dy: float,
                fill=(255, 255, 255, 255)) -> Image.Image:
    """Sub-pixel translate; the vacated strip is filled with ``fill``.

    ``fill`` must be OPAQUE for a white-background sheet - a transparent fill is
    later flattened to black and shows up as the dark edge.  Only a genuine
    transparency sheet should pass ``(0, 0, 0, 0)``.
    """
    if abs(dx) < 0.05 and abs(dy) < 0.05:
        return im
    w, h = im.size
    if im.mode == "RGBA":
        f = tuple(fill)[:3] + (255,) if len(tuple(fill)) < 4 else tuple(fill)
    else:
        f = tuple(fill)[:3]
    return im.transform((w, h), Image.AFFINE, (1, 0, -dx, 0, 1, -dy),
                        resample=Image.BILINEAR, fillcolor=f)


def stabilize(frames: list[Image.Image], stats: list[FrameStat], kind: str,
              axis: str, strength: float = 1.0,
              fill=(255, 255, 255, 255)) -> tuple[list[Image.Image], dict]:
    """Remove slow positional drift without flattening the real animation.

    * pose-change : the subject should sit still while it turns, so ANY slow centroid
      trend is an artefact -> high-pass both axes.
    * translation : the active axis *is* the animation.  With ~16 frames and a full
      oscillation cycle, drift and motion are not separable there, so we leave that
      axis untouched and only strip drift from the other one.  Getting this wrong is
      how you "stabilise" a float animation into a static image.
    """
    n = len(frames)
    if n < 5:
        return frames, {"applied": False, "reason": "too few frames"}

    bx = np.array([s.bx for s in stats])
    by = np.array([s.by for s in stats])
    win = max(3, (n // 2) | 1)

    if kind == "pose-change":
        axes = ("x", "y")
    elif kind == "translation":
        axes = ("x",) if axis == "y" else ("y",)
    else:
        return frames, {"applied": False, "reason": "static"}

    res = {}
    dx = np.zeros(n)
    dy = np.zeros(n)
    if "x" in axes:
        t = moving_trend(bx, win)
        dx = -(t - bx.mean()) * strength
        res["x_drift_px"] = round(float(np.abs(t - bx.mean()).max()), 1)
    if "y" in axes:
        t = moving_trend(by, win)
        dy = -(t - by.mean()) * strength
        res["y_drift_px"] = round(float(np.abs(t - by.mean()).max()), 1)

    out = [shift_frame(f, dx[i], dy[i], fill) for i, f in enumerate(frames)]
    res["applied"] = bool(np.abs(dx).max() > 0.2 or np.abs(dy).max() > 0.2)
    res["kind"] = kind
    res["axis_kept"] = axis
    return out, res


def anchor_shift(frames: list[Image.Image], stats: list[FrameStat],
                 fill=(255, 255, 255, 255)) -> tuple[list[Image.Image], dict]:
    """ONE constant shift for the entire sequence. Jitter-free by construction.

    Per-frame stabilisation moves every frame by a *different* amount, so any error in
    the estimated drift becomes frame-to-frame jitter. Measured on a real reveal shot:
    the pose jitter index climbs from 1.87 (raw) to 2.22 with ``stabilize()`` on, and
    returns to 1.88 with it off. A single constant offset cannot do that - all
    frame-to-frame relationships survive exactly - so it only recentres the whole clip.
    """
    n = len(frames)
    if n < 2:
        return frames, {"applied": False, "reason": "too few frames"}
    w, h = frames[0].size
    bx = float(np.mean([s.bx for s in stats]))
    by = float(np.mean([s.by for s in stats]))
    dx, dy = (w - 1) / 2.0 - bx, (h - 1) / 2.0 - by
    if abs(dx) < 0.5 and abs(dy) < 0.5:
        return frames, {"applied": False, "reason": "already centred", "mode": "anchor"}
    out = [shift_frame(f, dx, dy, fill) for f in frames]
    return out, {"applied": True, "mode": "anchor",
                 "dx": round(dx, 1), "dy": round(dy, 1)}


# -------------------------------------------------------------- loop building


def loop_cut_index(stats: list[FrameStat], min_frac: float = 0.5,
                   max_dist: float = 0.30) -> int | None:
    """Find the cell whose pose best matches cell 1, so the tail can be cut there.

    Used for rotations: the model's 16th cell is usually mid-turn, so the loop snaps.
    Cutting at the best-matching pose trades a little rotation range for a clean loop.
    """
    d = [s.desc for s in stats]
    if not d or d[0] is None:
        return None
    start = max(2, int(len(d) * min_frac))
    best, best_i = None, None
    for i in range(start, len(d)):
        if d[i] is None:
            continue
        dist = float(np.linalg.norm(d[i] - d[0]))
        if best is None or dist < best:
            best, best_i = dist, i
    if best is None or best > max_dist:
        return None
    return best_i


def build_loop(frames: list[Image.Image], stats: list[FrameStat], mode: str,
               kind: str, axis: str) -> tuple[list[Image.Image], str, dict]:
    """Return (frames, mode_used, info)."""
    n = len(frames)
    info = {}
    if mode == "none" or n < 4:
        return frames, "none", info

    if mode in ("auto", "halfloop") and kind == "translation":
        win = max(3, (n // 3) | 1)
        sig = np.array([s.cy if axis == "y" else s.cx for s in stats], dtype=float)
        sm = moving_trend(sig, win)
        d = np.diff(sm)
        thr = max(abs(d).max() * 0.10, 1e-6)
        sign, end = 0, 0
        for i, v in enumerate(d):
            if abs(v) < thr:
                end = i + 2
                continue
            s = 1 if v > 0 else -1
            if sign == 0:
                sign = s
            elif s != sign:
                break
            end = i + 2
        ext = end - 1 if 1 <= end - 1 <= n - 3 else None
        if ext:
            loop = frames[:ext + 1] + frames[ext - 1:0:-1]
            info["halfloop_extremum"] = ext
            return loop, f"halfloop@{ext}", info
        if mode == "halfloop":
            raise SystemExit("halfloop requested but no monotone half cycle found")

    if mode in ("auto", "loopcut"):
        cut = loop_cut_index(stats)
        if cut:
            info["loopcut_index"] = cut
            return frames[:cut + 1], f"loopcut@{cut}", info
        if mode == "loopcut":
            raise SystemExit("loopcut requested but no matching pose found")

    if mode == "pingpong":
        return frames + frames[-2:0:-1], "pingpong", info

    return frames, "cycle", info


# ------------------------------------------------------------------- export


def fit_canvas(im: Image.Image, canvas_bg, canvas: str = "square") -> Image.Image:
    if canvas == "tight":
        return im
    w, h = im.size
    s = max(w, h)
    out = Image.new(im.mode, (s, s), canvas_bg)
    out.paste(im, ((s - w) // 2, (s - h) // 2), im if im.mode == "RGBA" else None)
    return out


def shared_palette(frames: list[Image.Image], n_colors: int = 255,
                   bg=(255, 255, 255)) -> Image.Image:
    thumbs = []
    for f in frames:
        t = flatten_rgb(f, bg)
        t.thumbnail((140, 140))
        thumbs.append(np.asarray(t))
    h = max(t.shape[0] for t in thumbs)
    w = sum(t.shape[1] for t in thumbs)
    mosaic = np.full((h, w, 3), 255, dtype=np.uint8)
    x = 0
    for t in thumbs:
        mosaic[:t.shape[0], x:x + t.shape[1]] = t
        x += t.shape[1]
    return Image.fromarray(mosaic).quantize(colors=max(2, min(n_colors, 255)),
                                            method=Image.MEDIANCUT)


def quantize_frames(frames: list[Image.Image], n_colors: int, transparent: bool,
                    dither: bool = True, bg=(255, 255, 255)) -> list[Image.Image]:
    pal = shared_palette(frames, n_colors, bg)
    dm = Image.FLOYDSTEINBERG if dither else Image.NONE
    out = []
    for f in frames:
        q = flatten_rgb(f, bg).quantize(palette=pal, dither=dm)
        if transparent:
            lut = (q.getpalette() or [])
            lut = (lut + [0] * 768)[:768]
            lut[765:768] = [255, 255, 255]          # index 255 == transparent
            q.putpalette(lut)
            a = f.getchannel("A").point(lambda v: 255 if v > 128 else 0)
            q.paste(255, mask=Image.eval(a, lambda v: 255 - v))
        out.append(q)
    return out


def write_gif(frames_p: list[Image.Image], path: str, duration: int | list[int],
              transparent: bool, optimize: bool = True) -> int:
    kw = dict(save_all=True, append_images=frames_p[1:], duration=duration, loop=0,
              disposal=2 if transparent else 1, optimize=optimize)
    if transparent:
        kw["transparency"] = 255
    frames_p[0].save(path, **kw)
    return os.path.getsize(path)


def even_durations(frames: list[Image.Image], base_ms: int,
                   floor_ms: int = 60, ceil_ms: int = 180,
                   size: int = 40) -> list[int]:
    """Per-frame dwell times that turn an uneven pose sampling into constant velocity.

    The model does not sample a move at equal intervals. Measured pose steps on a real
    reveal sheet run ``0.40 0.48 0.40 0.17 0.17 0.09 ...`` - the first three cells cover
    roughly a third of the whole 180 degree move. Playing every cell for the same 70 ms
    therefore reads as "lurch, then crawl", which is exactly what the eye reports as
    jitter-plus-uneven-speed.

    Weighting each cell's dwell time by how much it actually changes equalises the
    *apparent* speed without touching a single pixel: no resampling, no interpolation
    ghosting, no blur. Cell ``i`` is shown for the time it takes the move to travel from
    cell ``i`` to cell ``i+1`` (the last cell wraps to the first, so the seam is timed too).

    ``floor_ms`` is not cosmetic: a GIF delay is measured in centiseconds, and players
    routinely ignore frames shorter than ~50 ms, which shows up as flicker. Results are
    snapped to 10 ms so the value that reaches the file is the value computed here.
    """
    n = len(frames)
    if n < 3:
        return [base_ms] * n
    thumbs = [np.asarray(f.convert("L").resize((size, size), Image.BILINEAR),
                         dtype=np.float32) for f in frames]
    d = np.array([float(np.abs(thumbs[(i + 1) % n] - thumbs[i]).mean()) for i in range(n)])
    d = np.maximum(d, 1e-3)
    ms = np.clip(base_ms * (d / d.mean()), floor_ms, ceil_ms)
    return [int(round(v / 10.0) * 10) for v in ms]


def ramp_durations(frames: list[Image.Image], base_ms: int,
                   hi: float = 2.6, lo: float = 0.7, curve: float = 1.8,
                   floor_ms: int = 60, ceil_ms: int = 240) -> list[int]:
    """Dwell times that open slow and finish fast.

    The opening pose is the one the viewer is supposed to actually read, so it is held
    longest; the move then gathers speed so the rest of the arc goes past without
    dawdling. ``curve`` > 1 keeps the first few cells near the slow end for a little
    while, so the acceleration builds gradually instead of starting to ramp at once.

    This is a *pacing* choice, not a correctness fix - it does not claim to equalise
    speed. Use ``even_durations`` when the goal is constant apparent velocity.
    """
    n = len(frames)
    if n < 2:
        return [base_ms] * n
    t = np.linspace(0.0, 1.0, n)
    w = hi - (hi - lo) * (t ** curve)
    ms = np.clip(base_ms * w, floor_ms, ceil_ms)
    return [int(round(v / 10.0) * 10) for v in ms]


def resize_all(frames: list[Image.Image], size: int) -> list[Image.Image]:
    base = max(frames[0].size)
    sc = size / base
    return [f.resize((max(1, round(f.width * sc)), max(1, round(f.height * sc))),
                     Image.LANCZOS) for f in frames]


def export_webp(frames: list[Image.Image], path: str, duration: int | list[int],
                quality: int = 88, transparent: bool = False,
                bg=(255, 255, 255)) -> int:
    src = frames if transparent else [flatten_rgb(f, bg) for f in frames]
    src[0].save(path, save_all=True, append_images=src[1:], duration=duration,
                loop=0, lossless=False, quality=quality, method=6)
    return os.path.getsize(path)


def export_mp4(frames: list[Image.Image], path: str, fps: int = 25) -> int | None:
    tmp = path + "_frames"
    os.makedirs(tmp, exist_ok=True)
    for i, f in enumerate(frames, 1):
        bg = Image.new("RGB", f.size, (255, 255, 255))
        if f.mode == "RGBA":
            bg.paste(f, mask=f.getchannel("A"))
        else:
            bg = f.convert("RGB")
        bg.save(os.path.join(tmp, f"f{i:04d}.png"))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
           "-i", os.path.join(tmp, "f%04d.png"), "-c:v", "libx264",
           "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
           "-loop", "0", path]
    try:
        subprocess.run(cmd, check=True)
        size = os.path.getsize(path)
    except Exception:
        size = None
    for name in os.listdir(tmp):
        os.remove(os.path.join(tmp, name))
    os.rmdir(tmp)
    return size
