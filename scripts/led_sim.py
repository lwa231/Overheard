#!/usr/bin/env python3
"""Preview the LED-matrix animation skins without the board.

  python3 scripts/led_sim.py --pattern fish --seconds 8      # ANSI blocks in the terminal
  python3 scripts/led_sim.py --html shots/led-sim.html       # one self-contained page, all patterns side by side
  python3 scripts/led_sim.py --html shots/led-sim.html --png shots/led-sim.png   # also a screenshot (needs playwright)

Frames come from src/overheard/ledanim.py, the same generators that are baked into the board's sketch.
"""
import argparse
import html
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from overheard import ledanim  # noqa: E402

SHADE = (236, 24, 33, 39)   # 256-colour codes for levels 0..3 (dark grey to bright blue-white)

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Overheard LED simulator</title><style>
:root{color-scheme:dark;--bg:#0b0d12;--card:#141821;--ink:#e8ecf4;--dim:#8a93a6;--acc:#4da3ff}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.4 system-ui,sans-serif;padding:24px 16px}
h1{font-size:20px;margin:0 0 4px}p{color:var(--dim);margin:0 0 20px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}
.card{background:var(--card);border-radius:14px;padding:14px;border:1px solid #232a38}
.card h2{font-size:15px;margin:0 0 10px;display:flex;justify-content:space-between}
.card h2 span{color:var(--dim);font-weight:400;font-size:12px}
canvas{width:100%;aspect-ratio:13/8;display:block;background:#05070a;border-radius:8px}
button{background:var(--card);color:var(--ink);border:1px solid #232a38;border-radius:8px;padding:6px 12px;font:inherit;cursor:pointer}
</style></head><body><h1>Overheard LED simulator</h1>
<p>__W__ &times; __H__ matrix, 4 brightness levels, __MS__ ms per frame. Generated from ledanim.py. <button id="pp">Pause</button></p>
<div class="grid" id="g"></div><script>
const W=__W__,H=__H__,MS=__MS__,A=__DATA__,LV={'.':0,'1':.3,'2':.6,'3':1};let on=true;
const g=document.getElementById('g'),cards=[];
for(const k in A){const c=document.createElement('div');c.className='card';c.innerHTML='<h2>'+A[k].name+'<span></span></h2><canvas width="520" height="320"></canvas>';
 g.appendChild(c);cards.push({f:A[k].frames,cv:c.querySelector('canvas'),lab:c.querySelector('span'),i:0})}
function draw(o){const x=o.cv.getContext('2d'),d=Math.min(520/W,320/H),ox=(520-d*W)/2,oy=(320-d*H)/2,fr=o.f[o.i];x.clearRect(0,0,520,320);
 for(let r=0;r<H;r++)for(let c=0;c<W;c++){const v=LV[fr[r][c]];x.beginPath();x.arc(ox+(c+.5)*d,oy+(r+.5)*d,d*.38,0,7);
  x.fillStyle=v?'rgba(77,163,255,'+(.3+.7*v)+')':'rgba(138,147,166,.14)';if(v){x.shadowColor='#4da3ff';x.shadowBlur=14*v}else x.shadowBlur=0;x.fill()}
 o.lab.textContent=(o.i+1)+' / '+o.f.length}
function tick(){if(on)cards.forEach(o=>{o.i=(o.i+1)%o.f.length});cards.forEach(draw)}
document.getElementById('pp').onclick=e=>{on=!on;e.target.textContent=on?'Pause':'Play'};
setInterval(tick,MS);tick();
</script></body></html>"""


def terminal(name, seconds, seed):
    frames = ledanim.render(name, seed)
    sys.stdout.write("\x1b[?25l")
    try:
        end, i = time.time() + seconds, 0
        while time.time() < end:
            fr = frames[i % len(frames)]
            out = ["\x1b[H\x1b[2J%s  frame %d/%d" % (name, i % len(frames) + 1, len(frames))]
            for row in fr:
                out.append("".join("\x1b[38;5;%dm██" % SHADE[ledanim.GLYPH.index(c)] for c in row) + "\x1b[0m")
            sys.stdout.write("\n".join(out) + "\n")
            sys.stdout.flush()
            time.sleep(ledanim.FRAME_MS / 1000)
            i += 1
    finally:
        sys.stdout.write("\x1b[0m\x1b[?25h\n")


def write_html(path, seed):
    data = {k: {"name": v[0], "frames": ledanim.render(k, seed)} for k, v in ledanim.ANIMS.items()}
    page = (PAGE.replace("__W__", str(ledanim.W)).replace("__H__", str(ledanim.H)).replace("__MS__", str(ledanim.FRAME_MS))
            .replace("__DATA__", json.dumps(data, separators=(",", ":")).replace("</", "<\\/")))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        f.write(page)
    return html.escape(path)


def screenshot(src, png, frames=None):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception:                     # bundled browser not installed: use the system Chrome
            b = p.chromium.launch(channel="chrome")
        pg = b.new_page(viewport={"width": 1100, "height": 760})
        pg.goto("file://" + os.path.abspath(src))
        pg.click("#pp")                       # pause on a fixed frame range, then step to a lively moment
        pg.evaluate("n=>{cards.forEach(o=>{o.i=Math.min(n,o.f.length-1);draw(o)})}", frames if frames is not None else 14)
        pg.screenshot(path=png, full_page=True)
        b.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pattern", choices=sorted(ledanim.ANIMS), help="pattern to show in the terminal")
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--html", metavar="OUT", help="write one self-contained HTML page with all patterns")
    ap.add_argument("--png", metavar="OUT", help="with --html: also save a screenshot (needs playwright)")
    a = ap.parse_args(argv)
    if a.html:
        write_html(a.html, a.seed)
        print("wrote", a.html)
        if a.png:
            screenshot(a.html, a.png)
            print("wrote", a.png)
    elif a.pattern:
        terminal(a.pattern, a.seconds, a.seed)
    else:
        ap.error("give --pattern NAME or --html OUT")


if __name__ == "__main__":
    main()
