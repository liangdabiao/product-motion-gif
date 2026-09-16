"""contact_sheet.py - numbered frame contact sheet, for human inspection.

    python contact_sheet.py out/sheet.jpg out/contact.png [rows cols] [cellw] [cellh]

The single artefact that makes a frame sheet reviewable: every cell laid out at a
readable size with its frame number, so pose / drift / framing problems are obvious.
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import giflab as G  # noqa: E402


def build(sheet_path: str, out_path: str, rows: int = 4, cols: int = 4,
          cell_w: int | None = None, pad: int = 44) -> str:
    sheet = G.load_image(sheet_path)
    frames = G.slice_sheet(sheet, rows, cols)
    cw, ch = frames[0].size
    if cell_w:
        sc = cell_w / cw
        cw, ch = cell_w, max(1, round(ch * sc))
    canvas = Image.new("RGB", (cols * cw, rows * (ch + pad)), (255, 255, 255))
    d = ImageDraw.Draw(canvas)
    for i, f in enumerate(frames):
        r, c = divmod(i, cols)
        y = r * (ch + pad)
        canvas.paste(f.convert("RGB").resize((cw, ch), Image.LANCZOS), (c * cw, y + pad))
        d.text((c * cw + 8, y + 14), f"frame {i + 1:02d}", fill=(20, 20, 20))
        d.rectangle([c * cw, y + pad, c * cw + cw - 1, y + pad + ch - 1], outline=(190, 190, 190))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    canvas.save(out_path)
    print(f"contact -> {out_path}  {canvas.size[0]}x{canvas.size[1]}")
    return out_path


if __name__ == "__main__":
    a = sys.argv[1:]
    build(a[0], a[1],
          int(a[2]) if len(a) > 2 else 4,
          int(a[3]) if len(a) > 3 else 4,
          int(a[4]) if len(a) > 4 else None)
