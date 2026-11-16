"""Deterministic LED-matrix animation skins (8 rows x 13 columns, brightness 0..3 as '.123').

Each generator builds one full loop for a fixed seed; the last frame leads cleanly back into the first.
tools/build_sprites.py bakes these into sprites.json (dashboard) and sprites.h (MCU), the same way as the
hand-drawn characters. Frame format is identical: 8 strings of 13 chars from '.123'.
"""
import itertools
import math
import random

W, H = 13, 8
GLYPH = ".123"
FRAME_MS = 120          # board and simulator step; the dashboard preview ticks at 140 ms


def _blank():
    return [[0] * W for _ in range(H)]


def _put(g, y, x, v):
    if 0 <= y < H and 0 <= x < W and v > g[y][x]:
        g[y][x] = v


def _text(g):
    return ["".join(GLYPH[v] for v in row) for row in g]


def matrix(rng):
    """Digital rain: every column loops with its own period (all divide 72), so the wrap is seamless."""
    L, tail = 72, (3, 2, 1, 1)
    cols = []
    for _ in range(W):
        period = rng.choice((24, 24, 36, 72))
        cycles = L // period
        active = [rng.random() < 0.8 for _ in range(cycles)]
        if not any(active):
            active[0] = True
        cols.append((period, rng.randrange(period), active))
    frames = []
    for t in range(L):
        g = _blank()
        for x, (period, off, active) in enumerate(cols):
            u = (t + off) % L
            if not active[u // period]:
                continue
            head = (u % period) * (H + len(tail)) // period      # 0..H+3 rows, head enters from above
            for k, v in enumerate(tail):
                _put(g, head - k, x, v)
        frames.append(_text(g))
    return frames


def stars(rng):
    """Quiet twinkling field plus one diagonal shooting star per loop."""
    L = 96
    pts = set()
    while len(pts) < 16:
        pts.add((rng.randrange(H), rng.randrange(W)))
    stars_ = [(y, x, rng.choice((12, 16, 24, 32, 48)), rng.randrange(96), rng.choice((1, 2, 2, 3)))
              for y, x in sorted(pts)]
    start_x, t0 = 1, 44
    frames = []
    for t in range(L):
        g = _blank()
        for y, x, per, ph, peak in stars_:
            f = ((t + ph) % per) / per                 # 0..1 triangle wave, peak in the middle
            tri = 1 - abs(2 * f - 1)
            v = int(round(tri * peak))
            _put(g, y, x, v if tri > 0.2 else 0)
        s = t - t0
        if 0 <= s < 18:                                # head moves down-right, 2-pixel tail
            hy, hx = s * 0.5, start_x + s * 0.75
            for k, v in enumerate((3, 2, 1)):
                _put(g, int(round(hy - k * 0.5)), int(round(hx - k * 0.75)), v)
        frames.append(_text(g))
    return frames


_FISH = {  # right-facing, (dy, dx, level); two tail poses
    "body": [(1, 1, 2), (1, 2, 3), (1, 3, 3), (1, 4, 2), (0, 2, 1), (0, 3, 2), (2, 2, 2), (2, 3, 1)],
    "a": [(0, 0, 2), (1, 0, 1)],
    "b": [(2, 0, 2), (1, 0, 1)],
}


def fish(rng):
    """Swims right, turns at the edge, swims back; tail flicks every other frame; two bubbles rise."""
    span, step, turn = W - 5, 2, 4                     # positions 0..8, one column per 2 frames
    L = 2 * (span * step + turn)
    path = []                                          # (x, facing)
    for d, xs in ((1, range(span + 1)), (-1, range(span, -1, -1))):
        for x in xs:
            path += [(x, d)] * step
        path += [(path[-1][0], d)] * (turn - step)
    bubbles = [rng.randrange(L) for _ in range(2)]
    frames = []
    for t in range(L):
        x0, d = path[t]
        y0 = 3 + (1 if (t // 8) % 2 else 0)
        g = _blank()
        for part in ("body", "a" if (t // 2) % 2 == 0 else "b"):
            for dy, dx, v in _FISH[part]:
                px = x0 + dx if d == 1 else x0 + 4 - dx
                _put(g, y0 + dy - 1, px, v)
        for bt in bubbles:
            s = (t - bt) % L
            if s < 6:                                  # rises from above the head, one row per frame
                bx = x0 + 4 if d == 1 else x0
                _put(g, y0 - 1 - s, bx, 2 if s < 4 else 1)
        frames.append(_text(g))
    return frames


def _walk(rng, slots):
    """Closed wandering route of exactly `slots` cells: waypoints joined by king moves, with pauses."""
    while True:
        pts = [(rng.randrange(H), rng.randrange(W)) for _ in range(rng.randrange(3, 6))]
        route = []
        for a, b in zip(pts, pts[1:] + pts[:1], strict=True):
            y, x = a
            while (y, x) != b:
                y += (b[0] > y) - (b[0] < y)
                x += (b[1] > x) - (b[1] < x)
                route.append((y, x))
        if 0 < len(route) <= slots - 6:
            break
    pauses = slots - len(route)
    out = []
    marks = sorted(rng.sample(range(len(route)), min(len(route), 5)))
    share = [pauses // len(marks) + (i < pauses % len(marks)) for i in range(len(marks))]
    for i, cell in enumerate(route):
        out.append(cell)
        if i in marks:
            out += [cell] * share[marks.index(i)]
    return out


def ants(rng):
    """Three independent ants and a convoy of three that follow the leader's route; one step per 2 frames."""
    slots = 60
    walkers = [(_walk(rng, slots), 0, 3) for _ in range(3)]
    lead = _walk(rng, slots)
    walkers += [(lead, -lag, v) for lag, v in ((0, 3), (3, 2), (6, 2))]
    frames = []
    for t in range(slots * 2):
        g = _blank()
        for route, lag, v in walkers:
            y, x = route[(t // 2 + lag) % slots]
            _put(g, y, x, v)
        frames.append(_text(g))
    return frames


def meteor(rng):
    """Three streaks in from the top at staggered times, each bursts where it lands; then a short dark gap."""
    fall, burst, dark = 10, 7, 5
    cy = H - 1
    cols = rng.sample(range(3, W), 3)
    starts = [0, 3 + rng.randrange(2), 7 + rng.randrange(2)]
    total = max(starts) + fall + burst + dark
    frames = []
    for t in range(total):
        g = _blank()
        for t0, cx in zip(starts, cols, strict=True):
            u = t - t0
            if 0 <= u < fall:
                hy, hx = cy - (fall - 1 - u), cx - (fall - 1 - u)
                for k, v in enumerate((3, 2, 1, 1)):
                    _put(g, hy - k, hx - k, v)
            elif fall <= u < fall + burst:
                sb = u - fall
                r = 0.6 + sb * 0.6
                level = 3 if sb < 2 else 2 if sb < 4 else 1
                for y in range(H):
                    for x in range(W):
                        d = math.hypot(y - cy, (x - cx) * 0.8)
                        if r - 1.1 < d <= r and not (sb == burst - 1 and rng.random() < 0.5):
                            _put(g, y, x, level)
                if sb < 2:
                    _put(g, cy, cx, 3)
        frames.append(_text(g))
    return frames

ANIMS = {"matrix": ("Matrix", matrix), "stars": ("Stars", stars), "fish": ("Fish", fish),
         "ants": ("Ants", ants), "meteor": ("Meteor", meteor)}


def render(name, seed=0):
    """One full loop as a list of frames (each: 8 strings of 13 chars from '.123')."""
    return ANIMS[name][1](random.Random("%s:%s" % (name, seed)))


def iter_frames(name, seed=0):
    """Endless frame stream: the loop repeats forever."""
    return itertools.cycle(render(name, seed))
