"""ab_frames.py - put two frames of a sheet side by side, enlarged, to judge motion.

The single most useful check when "it doesn't look like it is turning": pull cell 1 and
cell 16 (or cell 8 and cell 16) out of the sheet at 2x and look at them together. Numbers
say whether something changed; the pair says whether it changed the way you wanted.

    python ab_frames.py sheet.jpg out.png i j [rows cols] [cellw]

Example - did the camera really orbit 60 degrees?
    python ab_frames.py out/sheet.jpg out/ab-01-16.png 1 16 4 4 460

Only the two requested cells are cut out - slicing all sixteen would hold a full copy of
the sheet twice over, which is the difference between working and MemoryError on a 4K
sheet when the machine is already short of RAM.
"""
import sys

from PIL import Image, ImageDraw

sheet, out = sys.argv[1], sys.argv[2]
i, j = int(sys.argv[3]), int(sys.argv[4])
rows = int(sys.argv[5]) if len(sys.argv) > 5 else 4
cols = int(sys.argv[6]) if len(sys.argv) > 6 else 4
cellw = int(sys.argv[7]) if len(sys.argv) > 7 else 620

im = Image.open(sheet)
if im.mode != "RGB":
    im = im.convert("RGB")
W, H = im.size
cw, ch = W // cols, H // rows


def one(idx):
    idx = max(1, min(rows * cols, idx))
    r, c = (idx - 1) // cols, (idx - 1) % cols
    return im.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))


a, b = one(i), one(j)
del im
h = int(a.height * (cellw / a.width))

pad, lab = 16, 40
canvas = Image.new("RGB", (cellw * 2 + pad * 3, h + lab + pad * 2), (255, 255, 255))
d = ImageDraw.Draw(canvas)
for k, (idx, cell) in enumerate(((i, a), (j, b))):
    x = pad + k * (cellw + pad)
    canvas.paste(cell.resize((cellw, h), Image.LANCZOS), (x, lab + pad // 2))
    d.text((x + 4, 14), "frame %02d" % idx, fill=(20, 20, 20))
canvas.save(out)
print("ab ->", out, canvas.size)
