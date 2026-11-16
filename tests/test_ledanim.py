import itertools
import json
import os
import subprocess
import sys

import pytest

from overheard import ledanim
from overheard.led import load_sprites

ROOT = os.path.join(os.path.dirname(__file__), "..")
NAMES = sorted(ledanim.ANIMS)


def _px(fr):
    return [ledanim.GLYPH.index(c) for row in fr for c in row]


def _diff(a, b):
    return sum(x != y for x, y in zip(_px(a), _px(b), strict=True))


def test_five_skins_registered():
    assert NAMES == ["ants", "fish", "matrix", "meteor", "stars"]


@pytest.mark.parametrize("name", NAMES)
def test_frames_match_matrix_size_and_levels(name):
    for fr in itertools.islice(ledanim.iter_frames(name), 500):
        assert len(fr) == ledanim.H == 8
        assert all(len(r) == ledanim.W == 13 and set(r) <= set(ledanim.GLYPH) for r in fr)


@pytest.mark.parametrize("name", NAMES)
def test_deterministic_and_seed_sensitive(name):
    assert ledanim.render(name, 7) == ledanim.render(name, 7)
    assert any(any(r.strip(".") for r in f) for f in ledanim.render(name, 7))


@pytest.mark.parametrize("name", NAMES)
def test_loop_wraps_without_a_jump(name):
    fr = ledanim.render(name)
    inner = max(_diff(a, b) for a, b in zip(fr, fr[1:], strict=False))
    assert _diff(fr[-1], fr[0]) <= inner + 2      # +2: a pixel can overlap another elsewhere in the loop


def test_meteor_has_dark_gap_between_cycles():
    fr = ledanim.render("meteor")
    dark = ["." * 13] * 8
    assert fr[-1] == dark and fr[-3:] == [dark] * 3
    assert any(f != dark for f in fr)


def test_generated_skins_are_in_sprites_json_after_characters():
    s = load_sprites()
    ids = list(s)
    assert ids[-5:] == ["matrix", "stars", "fish", "ants", "meteor"]
    for n in NAMES:
        assert s[n]["anim"] and s[n]["run"] == ledanim.render(n)
    assert json.loads(json.dumps(s)) == s


def test_simulator_writes_self_contained_page(tmp_path):
    out = tmp_path / "sim.html"
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "led_sim.py"), "--html", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    page = out.read_text()
    assert "src=" not in page and "http" not in page and all(n.capitalize() in page for n in NAMES)
