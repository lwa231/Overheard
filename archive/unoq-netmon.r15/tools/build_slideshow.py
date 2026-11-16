#!/usr/bin/env python3
"""Build a flip-through slideshow of UI options from screenshots (scripts/skin_shots.py).
usage: python3 tools/build_slideshow.py SHOTS_DIR OUT_DIR
Keys: arrows = move, space/enter = star, 1-5 = rate, e = copy picks as JSON (the data for a taste profile)."""
import json
import os
import re
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
shots, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
notes = json.load(open(os.path.join(ROOT, "design", "notes.json")))
ids = re.findall(r"id:'([a-z0-9-]+)',name:'([^']+)'", open(os.path.join(ROOT, "src/overheard/web/skins.js")).read())
slides = []
for sid, name in ids:
    for tag in ("lg", "sm"):
        src = os.path.join(shots, "%s-%s.png" % (sid, tag))
        Image.open(src).convert("RGB").save(os.path.join(out, "%s-%s.jpg" % (sid, tag)), quality=80, optimize=True)
    n = notes.get(sid, {})
    slides.append({"id": sid, "name": name, "blurb": n.get("blurb", ""), "refs": n.get("refs", "")})
html = open(os.path.join(ROOT, "design", "slideshow.tpl.html")).read().replace("__SLIDES__", json.dumps(slides))
open(os.path.join(out, "index.html"), "w").write(html)
print("slides:", len(slides))
