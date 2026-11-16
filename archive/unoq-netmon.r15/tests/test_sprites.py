import os
import subprocess
import sys

from overheard.led import load_sprites

ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_every_sprite_is_well_formed():
    for cid, s in load_sprites().items():
        assert len(s["run"]) >= 4 and len(s["sit"]) >= 2, cid
        for fr in s["run"] + s["sit"]:
            assert len(fr) == 8 and all(len(r) == 13 for r in fr), cid


def test_generated_files_are_current():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "build_sprites.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
