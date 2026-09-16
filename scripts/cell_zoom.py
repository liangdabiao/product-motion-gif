"""cell_zoom.py - zoom into the SAME region of several cells, side by side.

The ab_frames pair shows the whole frame; this shows one small part of it (a character,
a sign, a joint) across the whole sheet, which is how you tell whether something inside
the scene actually moved.

    python cell_zoom.py sheet.jpg out.png "1,5,9,13,16" x0,y0,x1,y1 [rows cols] [zoom] [label]

x0,y0,x1,y1 are fractions of the cell (0-1). Example - watch the monkey's ledge:
    python cell_zoom.py sheet.jpg out/walk.png "1,6,11,16" 0.55,0.02,1.0,0.42 4 4 2.5 monkey
"""
import sys

from PIL import Image, ImageDraw

sheet, out = sys.argv[1], sys.argv[2]
idxs = [int(v) for v in sys.argv[3].split(",")]
x0, y0, x1, y1 = (float(v) for v in sys.argv[4].split(","))
rows = int(sys.argv[5]) if len(sys.argv) > 5 else 4
cols = int(sys.argv[6]) if len(sys.argv) > 6 else 4
zoom = float(sys.argv[7]) if len(sys.argv) > 7 else 2.0
label = sys.argv[8] if len(sys.argv) > 8 else ""

im = Image.open(sheet)
if im.mode != "RGB":
    im = im.convert("RGB")
W, H = im.size
cw, ch = W // cols, H // rows
box = (int(cw * x0), int(ch * y0), int(cw * x1), int(ch * y1))
dw = max(1, int((box[2] - box[0]) * zoom))
dh = max(1, int((box[3] - box[1]) * zoom))

pad, lab = 14, 38
canvas = Image.new("RGB", (dw * len(idxs) + pad * (len(idxs) + 1), dh + lab + pad * 2),
                   (255, 255, 255))
d = ImageDraw.Draw(canvas)
for k, idx in enumerate(idxs):
    idx = max(1, min(rows * cols, idx))
    r, c = (idx - 1) // cols, (idx - 1) % cols
    cell = im.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)).crop(box)
    x = pad + k * (dw + pad)
    canvas.paste(cell.resize((dw, dh), Image.LANCZOS), (x, lab + pad // 2))
    d.text((x + 4, 12), ("%s " % label if label else "") + "f%02d" % idx, fill=(20, 20, 20))
canvas.save(out)
print("zoom ->", out, canvas.size, "cell", cw, "x", ch, "region", box)
