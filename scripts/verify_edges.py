"""Measure the border of a GIF exactly as a viewer renders it.

GIF frames are not independent: with disposal != 2 each frame is painted over the
previous one, so an artefact can come from compositing rather than from any single frame.
This walks the animation the way a decoder does and inspects the outer ring.

What we are hunting for is a PURE-BLACK band.  When the stabiliser shifts a frame it has
to fill the vacated strip; if that fill is transparent, the later RGBA -> RGB conversion
flattens it to (0,0,0).  A real subject, a shadow or a coloured backdrop never goes dark on
all three channels at once, so near-black pixels are the reliable signature.

Do NOT judge the border by luminance: a blue studio background or a grey backdrop is
legitimately dark and would false-alarm on every such shot.

    python verify_edges.py <a.gif> [b.gif ...]
"""
import sys

import numpy as np
from PIL import Image, ImageSequence


def ring_arr(a):
    return np.concatenate([a[:2].reshape(-1, 3), a[-2:].reshape(-1, 3),
                           a[:, :2].reshape(-1, 3), a[:, -2:].reshape(-1, 3)])


def inspect(path):
    im = Image.open(path)
    size = im.size
    canvas = Image.new("RGBA", size, (255, 255, 255, 255))
    rings = []
    worst = 255.0
    worst_frame = -1
    n = 0
    for i, fr in enumerate(ImageSequence.Iterator(im), 1):
        canvas = Image.alpha_composite(canvas, fr.convert("RGBA"))
        a = np.asarray(canvas.convert("RGB"), dtype=np.int16)
        ring = ring_arr(a)
        rings.append(ring)
        m = float(ring.max(axis=1).min())      # darkest pixel, by its brightest channel
        if m < worst:
            worst, worst_frame = m, i
        n += 1
    allr = np.concatenate(rings)
    mean_rgb = [round(float(v), 1) for v in allr.mean(axis=0)]
    black_frac = float((allr.max(axis=1) < 45).mean())
    print(f"{path}")
    print(f"  frames={n} size={size}")
    print(f"  mean border RGB = {mean_rgb}  (luminance {sum(mean_rgb)/3:.0f})")
    print(f"  near-black border pixels = {black_frac*100:.1f}%   "
          f"(darkest pixel {worst:.0f} in frame {worst_frame})")
    verdict = ("PASS (border matches the canvas)" if black_frac <= 0.02
               else "FAIL (pure-black border band - the stabiliser filled with transparent)")
    print(f"  verdict: {verdict}")
    return black_frac


if __name__ == "__main__":
    for p in sys.argv[1:]:
        inspect(p)
        print()
