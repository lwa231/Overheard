import json
import os
import plistlib
import re
import struct
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))


def test_sketch_sprite_order_matches_agent_order():
    """python/main.py sends an index: sprites.h and sprites.json must list characters in the same order."""
    ids = re.search(r"SPRITE_IDS\[SPRITE_COUNT\] = \{(.*?)\}", open(os.path.join(ROOT, "led/app/sketch/sprites.h")).read()).group(1)
    header_ids = re.findall(r'"([^"]+)"', ids)
    assert header_ids == list(json.load(open(os.path.join(ROOT, "src/overheard/sprites.json"))))


def test_app_bundle(tmp_path):
    import build_app
    app = build_app.build(str(tmp_path))
    plist = plistlib.load(open(os.path.join(app, "Contents", "Info.plist"), "rb"))
    assert plist["CFBundleExecutable"] == "Overheard" and plist["CFBundleIconFile"] == "AppIcon"
    exe = os.path.join(app, "Contents", "MacOS", "Overheard")
    assert os.access(exe, os.X_OK)
    data = open(os.path.join(app, "Contents", "Resources", "AppIcon.icns"), "rb").read()
    assert data[:4] == b"icns" and struct.unpack(">I", data[4:8])[0] == len(data)


def test_scripts_are_valid_bash():
    import subprocess
    for s in ("run.sh", "setup.sh"):
        assert subprocess.run(["bash", "-n", os.path.join(ROOT, "scripts", s)]).returncode == 0
