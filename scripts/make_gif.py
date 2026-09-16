"""make_gif.py - frame sheet in, looping product animation out.

    python make_gif.py --sheet out/grid.png --outdir out/shoe \
        --rows 4 --cols 4 --size 420 --duration 65 \
        --bg auto --quality-report out/shoe/qa.json

Writes animation.gif (+ animation.webp, animation.mp4), the sliced frames and an
optional QA report. See giflab.py for the reasoning behind each stage.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PIL import Image

import giflab as G


def qa_report(frames, stats, bg, loop_mode, info):
    areas = np.array([s.area for s in stats], dtype=float)
    cx = np.array([s.cx for s in stats])
    cy = np.array([s.cy for s in stats])
    issues = []
    k = G.classify(stats)
    if k["area_cv"] > 0.12:
        issues.append(f"silhouette area varies {k['area_cv']*100:.1f}% - subject may be "
                      f"reshaping rather than moving (check the sheet)")
    if k["kind"] == "translation" and k["cx_range"] > 0.08 * frames[0].width:
        issues.append(f"unrequested horizontal wander {k['cx_range']:.0f}px")
    if not info and loop_mode == "auto":
        issues.append("no loop repair applied - verify the seam visually")

    # the outer ring of every frame must match the canvas colour.  A shift-fill that is
    # transparent flattens to PURE BLACK once the GIF converts to RGB, so the reliable
    # signature is near-black pixels - NOT low luminance.  A dark or saturated canvas
    # (a blue studio background, a grey backdrop) is legitimately dark, and judging it by
    # brightness false-alarms on every such shot.
    ring_min, ring_mean = 255.0, [255.0, 255.0, 255.0]
    ring_lum, ring_black_frac = 255.0, 0.0
    if frames and bg != "transparent":
        rings = []
        for f in frames:
            a = np.asarray(f.convert("RGB"), dtype=np.int16)
            rings.append(np.concatenate([a[:2].reshape(-1, 3), a[-2:].reshape(-1, 3),
                                         a[:, :2].reshape(-1, 3), a[:, -2:].reshape(-1, 3)]))
        allr = np.concatenate(rings)
        lum = allr.mean(axis=1)
        ring_min = float(allr.min())
        ring_mean = [round(float(v), 1) for v in allr.mean(axis=0)]
        ring_lum = round(float(lum.mean()), 1)
        # a real subject, a shadow or a coloured backdrop never goes dark on ALL three
        # channels at once; a transparent fill always does
        ring_black_frac = round(float((allr.max(axis=1) < 45).mean()), 4)
        if ring_black_frac > 0.02:
            issues.append(f"pure-black band on the canvas border "
                          f"({ring_black_frac*100:.0f}% of the ring is near-black) - the "
                          f"stabiliser filled with transparent instead of the canvas colour")

    d = float(np.linalg.norm(stats[-1].desc - stats[0].desc)) if stats[0].desc is not None else None
    return {
        "frames": len(frames),
        "cell_size": list(frames[0].size),
        "motion": k,
        "area_cv": round(float(areas.std() / areas.mean()), 4) if areas.mean() else 0,
        "centroid": {"cx_range": round(float(cx.max() - cx.min()), 1),
                     "cy_range": round(float(cy.max() - cy.min()), 1)},
        "loop": dict(info) or {"mode": loop_mode},
        "seam_pose_distance": round(d, 3) if d is not None else None,
        "border": {"darkest_channel": round(ring_min, 1), "mean_rgb": ring_mean,
                   "ring_luminance": ring_lum, "near_black_fraction": ring_black_frac},
        "issues": issues,
        "verdict": "PASS" if not issues else "REVIEW",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", required=True, help="frame sheet image (png/jpg/webp)")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--rows", type=int, default=4)
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--size", type=int, default=640, help="output px on the long edge")
    ap.add_argument("--duration", type=int, default=70, help="ms per frame (base timing)")
    ap.add_argument("--timing", default="ramp", choices=["even", "ramp", "none"],
                    help="ramp = open slow, accelerate to the end (default; holds the "
                         "opening pose long enough to read, then the rest of the arc goes "
                         "past briskly - this is the accepted look for showcase loops); "
                         "even = weight each frame's dwell by how much it actually moves, "
                         "for constant apparent speed; none = one flat delay")
    ap.add_argument("--ramp", default="2.6,0.7,1.8", metavar="HI,LO,CURVE",
                    help="ramp timing shape: first-frame multiplier, last-frame "
                         "multiplier, and curve exponent (>1 delays the acceleration)")
    ap.add_argument("--even-timing", dest="even_timing", action="store_true", default=None,
                    help=argparse.SUPPRESS)
    ap.add_argument("--no-even-timing", dest="even_timing", action="store_false",
                    help=argparse.SUPPRESS)
    ap.add_argument("--bg", default="auto",
                    help="auto | r,g,b | transparent  (use transparent for --transparency sheets)")
    ap.add_argument("--trim", default="union", choices=["union", "none"])
    ap.add_argument("--canvas", default="square", choices=["square", "tight"])
    ap.add_argument("--stabilize", default="off",
                    choices=["off", "anchor", "auto", "full"],
                    help="off = leave the frames alone (default; a per-frame shift adds "
                         "frame-to-frame jitter), anchor = one constant recentre, "
                         "auto/full = legacy per-frame drift removal")
    ap.add_argument("--loop", default="auto", choices=["auto", "none", "cycle", "pingpong",
                                                       "halfloop", "loopcut"])
    ap.add_argument("--colors", type=int, default=255)
    ap.add_argument("--resample", default="lanczos", choices=["lanczos", "nearest"],
                    help="lanczos (default) for photos and renders; NEAREST for PIXEL-ART "
                         "sheets, where a smooth filter destroys the sprite grid. If you "
                         "care about crisp pixels, also pass --size equal to the source "
                         "long edge so nothing is resampled at all.")
    ap.add_argument("--no-dither", dest="dither", action="store_false", default=True,
                    help="turn off Floyd-Steinberg dithering during quantisation. Pixel art "
                         "and flat-colour sprites read better without it - dithering sprays "
                         "speckle across flat areas and, under transparent backgrounds, "
                         "creates stray semi-opaque pixels along the silhouette.")
    ap.add_argument("--max-kb", type=int, default=3000,
                    help="auto-shrink GIF to fit this budget (0=off). 3000 = ~3 MB, the "
                         "accepted ceiling - shrinking below ~640px visibly softens the "
                         "image, so raise this before letting the size ladder bite")
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--keep-frames", action="store_true")
    ap.add_argument("--quality-report", default=None)
    ap.add_argument("--no-webp", action="store_true")
    ap.add_argument("--no-mp4", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    sheet = G.load_image(args.sheet)
    frames = G.slice_sheet(sheet, args.rows, args.cols)
    print(f"sheet {sheet.size[0]}x{sheet.size[1]} -> {args.cols}x{args.rows} "
          f"cells of {frames[0].size[0]}x{frames[0].size[1]}")

    transparent = args.bg == "transparent"
    if args.bg == "auto" and G.has_alpha(frames):
        transparent = True
        print("alpha detected in the sheet -> treating background as transparent")
    bg = "transparent" if transparent else args.bg

    # 1. one global crop
    if args.trim == "union":
        masks = [G.bg_mask(f, bg) for f in frames]
        box = G.union_bbox(masks)
        frames = [f.crop(box) for f in frames]
        print(f"global crop {box} -> {frames[0].size[0]}x{frames[0].size[1]}")

    bg_rgb = (255, 255, 255)
    canvas_bg = (0, 0, 0, 0) if transparent else bg_rgb + (255,)
    fill_rgba = (0, 0, 0, 0) if transparent else bg_rgb + (255,)
    frames = [G.fit_canvas(f, canvas_bg, args.canvas) for f in frames]

    # 2. measure, classify, stabilise, repair the loop
    stats = G.measure(frames, bg)
    kind = G.classify(stats)
    print(f"motion: {kind['kind']}  area_cv={kind['area_cv']*100:.1f}%  "
          f"cx_range={kind['cx_range']}px cy_range={kind['cy_range']}px")

    if args.stabilize != "off" and kind["kind"] != "static":
        if args.stabilize == "anchor":
            frames, sinfo = G.anchor_shift(frames, stats, fill=fill_rgba)
        else:
            frames, sinfo = G.stabilize(frames, stats, kind["kind"], kind["axis"],
                                        fill=fill_rgba)
        print(f"stabilize: {sinfo}")
        stats = G.measure(frames, bg)

    info = {}
    if args.loop != "none":
        frames, used, info = G.build_loop(frames, stats, args.loop, kind["kind"], kind["axis"])
        if used != "cycle":
            stats = G.measure(frames, bg)
        print(f"loop: {args.loop} -> {used}  ({len(frames)} frames)")

    base = frames[0].size
    rs = Image.NEAREST if args.resample == "nearest" else Image.LANCZOS
    scaled = G.resize_all(frames, args.size, resample=rs)

    if args.keep_frames:
        fdir = os.path.join(args.outdir, "frames")
        os.makedirs(fdir, exist_ok=True)
        for i, f in enumerate(scaled, 1):
            f.save(os.path.join(fdir, f"frame_{i:02d}.png"))
        print(f"frames -> {fdir} ({len(scaled)})")

    # 3. GIF with one shared palette, auto-shrunk to the byte budget
    durations = args.duration
    timing = args.timing
    if args.even_timing is not None:
        timing = "even" if args.even_timing else "none"
    try:
        r_hi, r_lo, r_curve = (float(v) for v in args.ramp.split(","))
    except ValueError:
        raise SystemExit("--ramp expects HI,LO,CURVE, e.g. 2.0,0.75,1.6")
    if timing == "even":
        durations = G.even_durations(frames, args.duration)
    elif timing == "ramp":
        durations = G.ramp_durations(frames, args.duration,
                                     hi=r_hi, lo=r_lo, curve=r_curve)
    if timing != "none":
        sp = max(durations) / max(1, min(durations))
        print(f"timing: {timing} dwell {min(durations)}-{max(durations)}ms "
              f"(spread {sp:.2f}x)")
    gif_path = os.path.join(args.outdir, "animation.gif")
    ladder = [(args.size, args.colors)]
    if args.max_kb:
        for s in (0.85, 0.72, 0.6, 0.5):
            for c in (192, 128, 96, 64):
                ladder.append((int(args.size * s), c))
    final_bytes, used_cfg = 0, (args.size, args.colors)
    for sz, cols in ladder:
        # honour --size verbatim.  Capping it at the source cell width (an earlier version
        # did `min(sz, max(base))`) silently pinned every GIF to the cell size and made the
        # GIF smaller than the WebP built from the same frames.
        sub = G.resize_all(frames, sz, resample=rs)
        pframes = G.quantize_frames(sub, cols, transparent, bg=bg_rgb,
                                    dither=args.dither)
        final_bytes = G.write_gif(pframes, gif_path, durations, transparent)
        used_cfg = (sz, cols)
        if not args.max_kb or final_bytes <= args.max_kb * 1024:
            break
    out_w, out_h = Image.open(gif_path).size
    print(f"gif  {gif_path}  {final_bytes/1024:.0f} KB  "
          f"({out_w}x{out_h} colors={used_cfg[1]} {len(scaled)} frames)")

    if not args.no_webp:
        webp = os.path.join(args.outdir, "animation.webp")
        n = G.export_webp(scaled, webp, durations, transparent=transparent,
                          bg=bg_rgb)
        print(f"webp {webp}  {n/1024:.0f} KB")

    if not args.no_mp4:
        mp4 = os.path.join(args.outdir, "animation.mp4")
        n = G.export_mp4(scaled, mp4, args.fps)
        print(f"mp4  {mp4}  {n/1024:.0f} KB" if n else "mp4 skipped (ffmpeg missing)")

    report = qa_report(frames, stats, bg, args.loop, info)
    report["output"] = {"gif_kb": round(final_bytes / 1024),
                        "gif_size": used_cfg[0], "gif_colors": used_cfg[1],
                        "frames": len(scaled), "duration_ms": args.duration,
                        "resample": args.resample, "dither": args.dither}
    report["output"]["stabilize"] = args.stabilize
    if timing != "none":
        report["output"]["timing"] = timing
        report["output"]["dwell_ms"] = list(durations)
    print("\nQA:", json.dumps({k: report[k] for k in
                               ("motion", "loop", "seam_pose_distance", "border",
                                "verdict", "issues")},
                              ensure_ascii=False, indent=2))
    if args.quality_report:
        os.makedirs(os.path.dirname(os.path.abspath(args.quality_report)), exist_ok=True)
        with open(args.quality_report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print("qa ->", args.quality_report)


if __name__ == "__main__":
    main()
