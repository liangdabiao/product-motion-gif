"""contact_sheet.py - numbered frame contact sheet, for human inspection.

    python contact_sheet.py out/sheet.jpg out/contact.png [rows cols] [cellw] [bg] [resample]

The single artefact that makes a frame sheet reviewable: every cell laid out at a
readable size with its frame number, so pose / drift / framing problems are obvious.

For a TRANSPARENT sheet the alpha must be composited, never dropped: ``convert("RGB")``
sends fully transparent pixels to pure BLACK, which paints a black plate behind every
cell and hides the silhouette you are trying to inspect.  The default background is a
CHECKERBOARD - the universal "this is transparent" pattern - and it also makes a white
or black fringe around the sprite immediately visible.
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import giflab as G  # noqa: E402


def bg_image(size: tuple[int, int], spec: str = "checker") -> Image.Image:
    """checker | white | dark | black | r,g,b"""
    w, h = size
    if spec == "checker":
        cell = 12
        a, b = (170, 176, 186), (206, 211, 219)
        out = Image.new("RGB", (w, h), a)
        d = ImageDraw.Draw(out)
        for y in range(0, h, cell):
            for x in range(0, w, cell):
                if ((x // cell) + (y // cell)) % 2:
                    d.rectangle([x, y, x + cell - 1, y + cell - 1], fill=b)
        return out
    if spec == "white":
        return Image.new("RGB", (w, h), (255, 255, 255))
    if spec == "dark":
        return Image.new("RGB", (w, h), (34, 38, 46))
    if spec == "black":
        return Image.new("RGB", (w, h), (0, 0, 0))
    return Image.new("RGB", (w, h), tuple(int(v) for v in spec.split(",")))


def is_transparent(im: Image.Image) -> bool:
    return im.mode == "RGBA" and im.getchannel("A").getextrema()[0] < 250


def build(sheet_path: str, out_path: str, rows: int = 4, cols: int = 4,
          cell_w: int | None = None, pad: int = 44, bg: str = "checker",
          resample: str = "lanczos") -> str:
    sheet = G.load_image(sheet_path)
    frames = G.slice_sheet(sheet, rows, cols)
    cw, ch = frames[0].size
    if cell_w:
        sc = cell_w / cw
        cw, ch = cell_w, max(1, round(ch * sc))
    rs = Image.NEAREST if resample == "nearest" else Image.LANCZOS

    canvas = Image.new("RGB", (cols * cw, rows * (ch + pad)), (255, 255, 255))
    d = ImageDraw.Draw(canvas)
    for i, f in enumerate(frames):
        r, c = divmod(i, cols)
        y = r * (ch + pad)
        tile = f.resize((cw, ch), rs)
        if is_transparent(tile):
            base = bg_image((cw, ch), bg)
            base.paste(tile, (0, 0), tile)
            tile = base
        else:
            tile = tile.convert("RGB")
        canvas.paste(tile, (c * cw, y + pad))
        d.text((c * cw + 8, y + 14), f"frame {i + 1:02d}", fill=(20, 20, 20))
        d.rectangle([c * cw, y + pad, c * cw + cw - 1, y + pad + ch - 1],
                    outline=(120, 120, 120))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    canvas.save(out_path)
    print(f"contact -> {out_path}  {canvas.size[0]}x{canvas.size[1]}  bg={bg}")
    return out_path


if __name__ == "__main__":
    a = sys.argv[1:]
    build(a[0], a[1],
          int(a[2]) if len(a) > 2 else 4,
          int(a[3]) if len(a) > 3 else 4,
          int(a[4]) if len(a) > 4 else None,
          bg=a[5] if len(a) > 5 else "checker",
          resample=a[6] if len(a) > 6 else "lanczos")
