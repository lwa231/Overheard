"""The 3DS admin page: served behind the token, ES5-only script (the New 3DS browser is old WebKit)."""
import http.client
import os
import re
import shutil
import subprocess
import threading

import pytest

from overheard import config
from overheard.server import App, serve
from overheard.state import State

PAGE = os.path.join(os.path.dirname(__file__), "..", "src", "overheard", "web", "3ds.html")
TOKEN = "t" * 32


def _script():
    text = open(PAGE, encoding="utf-8").read()
    ms = re.findall(r"<script[^>]*>(.*?)</script>", text, re.S | re.I)
    assert len(ms) == 1
    return ms[0]


@pytest.fixture
def server(tmp_path):
    cfg = config.parse(["--demo", "--data-dir", str(tmp_path)])
    app = App(cfg, State(), token=TOKEN, secret="abcdefghijkl")
    httpd = serve(app, "127.0.0.1", 0)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield httpd.server_address[1]
    httpd.shutdown()


def _get(port, path, cookie=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request("GET", path, headers={"Cookie": cookie} if cookie else {})
    r = c.getresponse()
    return r.status, r.read()


def test_served_behind_token(server):
    assert _get(server, "/3ds")[0] == 401
    st, body = _get(server, "/3ds", "ov=" + TOKEN)
    assert st == 200 and b"Overheard 3DS" in body and b"/api/unlock" in body


def test_script_parses():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not found")
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "s.js")
        open(f, "w", encoding="utf-8").write(_script())
        r = subprocess.run([node, "--check", f], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("pat", [r"=>", r"\blet\s", r"\bconst\s", r"fetch\(", r"`", r"Promise", r"classList", r"\$\{"])
def test_script_is_es5(pat):
    assert not re.search(pat, _script()), pat


def test_page_has_no_modern_layout_or_filter_control():
    t = open(PAGE, encoding="utf-8").read()
    assert not re.search(r"display\s*:\s*(flex|grid)|var\(--|@font-face|<script[^>]+src=", t)
    assert "filter" not in t.lower().replace("text-overflow", "")
