#!/usr/bin/env python3
"""Draws the app icon. `python3 logo.py sheet` previews every variant; `python3 logo.py build` writes icon-1024.png."""
import math
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

N = 2048   # draw big, shrink for smooth edges
RAMP = [(0, (91, 124, 255)), (.35, (34, 199, 221)), (.6, (124, 217, 87)), (.82, (255, 210, 63)), (1, (255, 120, 45))]
FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]


def ramp(t):
    for (a, ca), (b, cb) in zip(RAMP, RAMP[1:], strict=False):
        if t <= b:
            k = (t - a) / (b - a)
            return tuple(int(ca[i] + (cb[i] - ca[i]) * k) for i in range(3))
    return RAMP[-1][1]


def font(size):
    for f in FONTS:
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()


def squircle(size, r=0.225):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], int(size * r * 1.15), fill=255)
    return m


def vgrad(size, top, bot):
    g = Image.new("RGB", (size, size))
    d = ImageDraw.Draw(g)
    for y in range(size):
        k = y / size
        d.line([(0, y), (size, y)], fill=tuple(int(top[i] + (bot[i] - top[i]) * k) for i in range(3)))
    return g


def arcs(size, cx, cy, radii, width, a0, a1, color_fn, gap_dot=None):
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    for i, r in enumerate(radii):
        mask = Image.new("L", (size, size), 0)
        d = ImageDraw.Draw(mask)
        d.arc([cx - r, cy - r, cx + r, cy + r], a0, a1, fill=255, width=width)
        for ang in (a0, a1):      # round caps
            rc = r - width / 2
            x, y = cx + rc * math.cos(math.radians(ang)), cy + rc * math.sin(math.radians(ang))
            d.ellipse([x - width / 2, y - width / 2, x + width / 2, y + width / 2], fill=255)
        col = Image.new("RGBA", (size, size), color_fn(i, len(radii)) + (255,))
        layer = Image.alpha_composite(layer, Image.composite(col, Image.new("RGBA", (size, size), (0, 0, 0, 0)), mask))
    return layer


def glow(layer, rad, strength=0.8):
    g = layer.filter(ImageFilter.GaussianBlur(rad))
    a = g.getchannel("A").point(lambda v: int(v * strength))
    g.putalpha(a)
    return g


def tag(img, text, cx, cy, size, color, spacing=0.18):
    d = ImageDraw.Draw(img)
    f = font(size)
    widths = [d.textlength(ch, font=f) for ch in text]
    total = sum(widths) + size * spacing * (len(text) - 1)
    x = cx - total / 2
    for ch, w in zip(text, widths, strict=True):
        d.text((x, cy), ch, font=f, fill=color, anchor="lm")
        x += w + size * spacing


def base(top, bot):
    img = vgrad(N, top, bot).convert("RGBA")
    img.putalpha(squircle(N))
    return img


def finish(img):
    # soft inner highlight on the top edge, like a real macOS icon
    hl = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    ImageDraw.Draw(hl).rounded_rectangle([6, 6, N - 7, N - 7], int(N * .225 * 1.15), outline=(255, 255, 255, 46), width=8)
    img = Image.alpha_composite(img, hl)
    out = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    out.paste(img, (0, 0), squircle(N))
    return out.resize((1024, 1024), Image.LANCZOS)


def v_a():     # night, heat-ramp arcs, AWL pill
    img = base((24, 28, 52), (8, 9, 18))
    cx, cy = N // 2, int(N * .60)
    a = arcs(N, cx, cy, [int(N * k) for k in (.17, .295, .42)], int(N * .066), 225, 315, lambda i, n: ramp(.15 + .75 * i / (n - 1)))
    img = Image.alpha_composite(img, glow(a, 40))
    img = Image.alpha_composite(img, a)
    d = ImageDraw.Draw(img)
    r = int(N * .052)
    d.ellipse([cx - r, cy - r + int(N * .03), cx + r, cy + r + int(N * .03)], fill=(255, 255, 255))
    pill = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle([cx - 380, int(N * .805) - 120, cx + 380, int(N * .805) + 120], 120, fill=(255, 255, 255, 26), outline=(255, 255, 255, 80), width=6)
    img = Image.alpha_composite(img, pill)
    tag(img, "AWL", cx, int(N * .805) + 6, 210, (235, 240, 255, 255), .2)
    return finish(img)


def v_b():     # ear: arcs wrap a listening dot, brighter, paper tones
    img = base((247, 247, 250), (214, 218, 232))
    cx, cy = int(N * .5), int(N * .56)
    a = arcs(N, cx, cy, [int(N * k) for k in (.15, .26, .37)], int(N * .07), 215, 325, lambda i, n: ramp(.05 + .5 * i / (n - 1)))
    img = Image.alpha_composite(img, a)
    d = ImageDraw.Draw(img)
    r = int(N * .06)
    d.ellipse([cx - r, cy + int(N * .03) - r, cx + r, cy + int(N * .03) + r], fill=(24, 28, 52))
    tag(img, "AWL", cx, int(N * .80), 230, (24, 28, 52, 255), .12)
    return finish(img)


def v_c():     # deep gradient, thick arcs rising from a corner-anchored dot, monogram top
    img = base((70, 52, 200), (12, 16, 48))
    cx, cy = int(N * .30), int(N * .70)
    a = arcs(N, cx, cy, [int(N * k) for k in (.20, .34, .48)], int(N * .075), 270, 360, lambda i, n: ramp(.1 + .8 * i / (n - 1)))
    img = Image.alpha_composite(img, glow(a, 50, .9))
    img = Image.alpha_composite(img, a)
    d = ImageDraw.Draw(img)
    r = int(N * .07)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255))
    tag(img, "AWL", int(N * .66), int(N * .80), 200, (255, 255, 255, 235), .15)
    return finish(img)


def v_d():     # black, concentric rings (sound/ear) with AWL centre
    img = base((18, 18, 22), (0, 0, 0))
    cx = cy = N // 2
    for i, r in enumerate((.43, .34, .25)):
        layer = Image.new("RGBA", (N, N), (0, 0, 0, 0))
        col = ramp(.1 + .35 * i) + (255,)
        ImageDraw.Draw(layer).ellipse([cx - N * r, cy - N * r, cx + N * r, cy + N * r], outline=col, width=int(N * .035))
        img = Image.alpha_composite(img, glow(layer, 30, .7))
        img = Image.alpha_composite(img, layer)
    tag(img, "AWL", cx, cy, 300, (255, 255, 255, 255), .1)
    return finish(img)


VARIANTS = {"a": v_a, "b": v_b, "c": v_c, "d": v_d}

if __name__ == "__main__":
    if sys.argv[1] == "sheet":
        sheet = Image.new("RGB", (4 * 532, 532), (200, 200, 205))
        for i, k in enumerate(VARIANTS):
            im = VARIANTS[k]().resize((512, 512), Image.LANCZOS)
            sheet.paste(im, (10 + i * 532, 10), im)
        sheet.save("sheet.png")
    else:
        VARIANTS[sys.argv[2] if len(sys.argv) > 2 else "a"]().save("icon-1024.png")
