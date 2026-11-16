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


def _shipped_files():
    """Exactly what install.sh sends: `tar -C src --exclude __pycache__ -cf - overheard`."""
    import subprocess
    out = subprocess.run(["tar", "-C", os.path.join(ROOT, "src"), "--exclude", "__pycache__", "-cf", "-", "overheard"], capture_output=True, check=True).stdout
    import io
    import tarfile
    with tarfile.open(fileobj=io.BytesIO(out)) as t:
        return t.getnames()


EXPERIMENTAL = ("adstream.py", "live_capture.py", "live_youtube_traffic.py", "dpi_packet_filter.py", "netfilterqueue")


def test_install_script_ships_only_the_package():
    sh = open(os.path.join(ROOT, "scripts", "install.sh")).read()
    assert "tar -C src" in sh and "experimental" not in sh


def test_experimental_code_is_not_in_the_shipped_package(tmp_path):
    import tarfile
    names = _shipped_files()
    assert "overheard/__init__.py" in names
    assert not [n for n in names if os.path.basename(n) in EXPERIMENTAL or "experimental" in n]
    # a built .tgz of the package (same tar invocation, gzipped) must be clean too
    tgz = tmp_path / "overheard.tgz"
    import subprocess
    subprocess.run(["tar", "-C", os.path.join(ROOT, "src"), "--exclude", "__pycache__", "-czf", str(tgz), "overheard"], check=True)
    with tarfile.open(tgz) as t:
        assert not [n for n in t.getnames() if os.path.basename(n) in EXPERIMENTAL or "experimental" in n]


def test_src_never_imports_experimental_code():
    pkg = os.path.join(ROOT, "src", "overheard")
    for f in os.listdir(pkg):
        if f.endswith(".py"):
            text = open(os.path.join(pkg, f)).read()
            assert not re.search(r"^\s*(from|import)\s+(overheard\.)?(adstream|live_capture|dpi_packet_filter|live_youtube_traffic|experimental)\b", text, re.M), f
            assert "netfilterqueue" not in text, f
    assert not os.path.exists(os.path.join(pkg, "adstream.py")) and not os.path.exists(os.path.join(pkg, "live_capture.py"))
