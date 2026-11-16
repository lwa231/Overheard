"""r18: the board's address comes from board.conf / sites / environment, never hard-coded in the scripts."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def _resolve(env=None, extra=""):
    e = {k: v for k, v in os.environ.items() if not k.startswith(("BOARD", "SITE"))}
    e.update(env or {})
    cmd = 'set -eu; . scripts/board.sh; ' + extra + ' echo "$BOARD_DEFAULT|$BOARD_MDNS"'
    return subprocess.run(["bash", "-c", cmd], cwd=ROOT, env=e, capture_output=True, text=True)


def test_default_comes_from_board_conf():
    r = _resolve()
    assert r.returncode == 0 and r.stdout.strip() == "arduino@100.69.41.76|UnoQ1.local"


def test_env_overrides_conf():
    assert _resolve({"BOARD_HOST": "10.9.9.9"}).stdout.strip().startswith("arduino@10.9.9.9|")


def test_site_selects_a_file(tmp_path):
    site = os.path.join(ROOT, "sites", "zz_test.conf")
    open(site, "w").write("BOARD_USER=pi\nBOARD_HOST=10.1.1.2\nBOARD_MDNS=\n")
    try:
        assert _resolve({"SITE": "zz_test"}).stdout.strip() == "pi@10.1.1.2|"
    finally:
        os.remove(site)


def test_unknown_site_and_placeholder_fail_cleanly():
    r = _resolve({"SITE": "nope"})
    assert r.returncode != 0 and "No such site" in r.stdout
    r = _resolve({"BOARD_HOST": "CHANGE-ME"})
    assert r.returncode != 0 and "Set BOARD_HOST" in r.stdout


def test_no_script_hardcodes_the_address():
    names = ["Install Overheard.command", "Check Overheard.command", "Phone Test.command", "Install Tailscale on Board.command",
             "Install LED Sketch.command", "scripts/install.sh", "scripts/status.sh", "scripts/run.sh", "scripts/setup.sh", "Makefile"]
    for n in names:
        assert "100.69.41.76" not in open(os.path.join(ROOT, n)).read(), n


def test_profile_tool_follows_board_host(monkeypatch):
    import importlib

    import make_profile
    monkeypatch.setenv("BOARD_HOST", "10.4.4.4")
    assert importlib.reload(make_profile).BOARD == "10.4.4.4"
    monkeypatch.delenv("BOARD_HOST")
    assert importlib.reload(make_profile).BOARD == "100.69.41.76"
