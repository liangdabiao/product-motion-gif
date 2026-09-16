"""Side-by-side sharpness check: same cell from two sheets, normalised to one display size.

Usage:
    python compare_clear.py SHEET_A SHEET_B OUT.png [IDX] [ROWS] [COLS] [LONG] [LABEL_A] [LABEL_B]
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
]


def load_font(size):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def cell(path, idx, rows, cols):
    im = Image.open(path).convert("RGB")
    cw, ch = im.width // cols, im.height // rows
    idx = max(1, min(rows * cols, idx))
    r, c = (idx - 1) // cols, (idx - 1) % cols
    return im.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))


def fit_long(im, long_edge):
    if im.height >= im.width:
        return im.resize((round(im.width * long_edge / im.height), long_edge), Image.LANCZOS)
    return im.resize((long_edge, round(im.height * long_edge / im.width)), Image.LANCZOS)


def main():
    a_path, b_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
    idx = int(sys.argv[4]) if len(sys.argv) > 4 else 16
    rows = int(sys.argv[5]) if len(sys.argv) > 5 else 4
    cols = int(sys.argv[6]) if len(sys.argv) > 6 else 4
    long_edge = int(sys.argv[7]) if len(sys.argv) > 7 else 816
    la = sys.argv[8] if len(sys.argv) > 8 else "A"
    lb = sys.argv[9] if len(sys.argv) > 9 else "B"

    ca, cb = cell(a_path, idx, rows, cols), cell(b_path, idx, rows, cols)
    print(f"cell A {ca.size}  cell B {cb.size}")
    # normalise both to the same long edge so the smaller one is shown at the same
    # display size as the larger - that is exactly what the eye compares.
    a = fit_long(ca, long_edge)
    b = fit_long(cb, long_edge)

    font = load_font(26)
    bar = 44
    pad = 18
    W = a.width + b.width + pad * 3
    H = long_edge + bar + pad * 2
    canvas = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(canvas)

    ax, bx = pad, pad * 2 + a.width
    d.text((ax, 12), la, fill=(20, 20, 20), font=font)
    d.text((bx, 12), lb, fill=(20, 20, 20), font=font)
    canvas.paste(a, (ax, bar + pad))
    canvas.paste(b, (bx, bar + pad))
    d.rectangle([ax - 1, bar + pad - 1, ax + a.width, bar + pad + a.height], outline=(200, 200, 200))
    d.rectangle([bx - 1, bar + pad - 1, bx + b.width, bar + pad + b.height], outline=(200, 200, 200))

    canvas.save(out)
    print("saved", out, canvas.size)

    # a 2x detail crop of the same relative region from each, stacked side by side
    def detail(im):
        w, h = im.size
        box = (int(w * 0.32), int(h * 0.42), int(w * 0.86), int(h * 0.94))
        c = im.crop(box)
        return c.resize((c.width * 2, c.height * 2), Image.LANCZOS)

    da, db = detail(a), detail(b)
    W2 = da.width + db.width + pad * 3
    H2 = max(da.height, db.height) + bar + pad * 2
    c2 = Image.new("RGB", (W2, H2), (255, 255, 255))
    d2 = ImageDraw.Draw(c2)
    d2.text((pad, 12), la + "  (2x detail)", fill=(20, 20, 20), font=font)
    d2.text((pad * 2 + da.width, 12), lb + "  (2x detail)", fill=(20, 20, 20), font=font)
    c2.paste(da, (pad, bar + pad))
    c2.paste(db, (pad * 2 + da.width, bar + pad))
    out2 = out.replace(".png", "-detail.png")
    c2.save(out2)
    print("saved", out2, c2.size)


if __name__ == "__main__":
    main()
