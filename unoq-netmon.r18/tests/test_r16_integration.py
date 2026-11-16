"""r16: the seams between the guard, the lock, the settings file and the board scripts."""
import dataclasses
import http.client
import json
import os
import re
import shutil
import subprocess
import threading
import time

import pytest

from overheard import config, dnsproto
from overheard.adult import AdultFilter, FlagLog, Guard, PenaltyBox
from overheard.blocklist import Blocklist
from overheard.dnsserver import DnsServer
from overheard.server import App, Req, serve
from overheard.settings import Settings
from overheard.state import State

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = "t" * 32
BAD = "www.badsite.com"


@pytest.fixture
def rig(tmp_path):
    cfg = dataclasses.replace(config.parse(["--data-dir", str(tmp_path)]), penalty_delay=0.15)
    st = State(settings=Settings(cfg.data_dir))
    guard = Guard(AdultFilter({"badsite.com"}), PenaltyBox(90), FlagLog(str(tmp_path / "f.json")))
    dns = DnsServer(cfg, st, Blocklist(), lambda p: p, guard)
    app = App(cfg, st, guard=guard, token=TOKEN)
    return cfg, st, guard, dns, app


def j(res):
    return res[0], json.loads(res[2])


def test_locked_stats_keep_upstream_and_refused_for_the_page(rig):
    _, st, _, dns, app = rig
    st.note_refused("203.0.113.7")
    st.dns["tls"] = 1
    s, d = j(app.route("GET", "/api/stats"))
    assert s == 200 and d["unlocked"] is False and d["recent"] == []
    assert d["dns"]["upstream"] == "tls"
    assert d["refused"] == [{"id": "203.0.113.7", "count": 1, "last": d["refused"][0]["last"]}]
    assert "settings" not in d


def test_doctor_over_http_gets_recent_with_t_client_domain(rig):
    _, st, _, _, app = rig
    st.record("10.0.0.5", "example.org", False)
    httpd = serve(app, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        def get(**h):
            c = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)
            c.request("GET", "/api/stats", headers={"Cookie": "ov=" + TOKEN, **h})
            return json.loads(c.getresponse().read())
        d = get(**{"X-Overheard-Doctor": "1"})
        assert d["unlocked"] is False and d["recent"]
        assert {"t", "client", "domain"} <= set(d["recent"][0]) and d["recent"][0]["domain"] == "example.org"
        assert get()["recent"] == []
    finally:
        httpd.shutdown()


@pytest.mark.skipif(not shutil.which("bash"), reason="needs bash")
def test_status_script_reads_the_unlock_file_the_server_creates(tmp_path):
    home = tmp_path / "home"
    data = home / "netmon" / "data"
    cfg = config.parse(["--data-dir", str(data)])
    app = App(cfg, State())                                         # what __main__ does: the secret is created at start
    assert (data / "unlock").read_text().strip() == app.secret
    assert "--data-dir /home/arduino/netmon/data" in open(os.path.join(ROOT, "scripts", "install.sh")).read()
    script = open(os.path.join(ROOT, "scripts", "status.sh")).read()
    remote = re.search(r"<<'REMOTE'[^\n]*\n(.*?)\nREMOTE\n", script, re.S).group(1)
    out = subprocess.run(["bash", "-s"], input=remote, capture_output=True, text=True, env={**os.environ, "HOME": str(home), "PATH": os.environ["PATH"]}, timeout=30).stdout
    assert "Unlock secret for the dashboard: " + app.secret in out


def test_main_wires_persistent_settings_and_unlock_file(tmp_path, monkeypatch):
    from overheard import __main__ as m
    seen = {}
    real = m.App

    def spy(cfg, state, *a, **kw):
        seen["app"] = real(cfg, state, *a, **kw)
        return seen["app"]
    monkeypatch.setattr(m, "App", spy)
    monkeypatch.setattr(m, "serve", lambda *a: (_ for _ in ()).throw(OSError("no")))
    m.main(["--demo", "--no-profiles", "--port", "0", "--host", "127.0.0.1", "--data-dir", str(tmp_path)])
    app = seen["app"]
    assert app.state.settings.path == str(tmp_path / "settings.json")
    assert (tmp_path / "unlock").read_text().strip() == app.secret and oct(os.stat(tmp_path / "unlock").st_mode & 0o777) == "0o600"


def test_slowdown_set_through_the_api_drives_the_dns_server_and_persists(rig):
    cfg, st, guard, dns, app = rig
    sid = app.sessions.start()
    req = lambda: Req("10.0.0.7", "ovu=" + sid)       # noqa: E731
    dns.handle_packet(dnsproto.build_query(BAD), "10.0.0.5")
    t0 = time.monotonic()
    assert dns.slow_down("10.0.0.5") and time.monotonic() - t0 < 0.05
    assert app.route("POST", "/api/settings", b'{"slowdown": true}', Req("10.0.0.7"))[0] == 403
    assert not st.settings.slowdown
    assert j(app.route("POST", "/api/settings", b'{"slowdown": true}', req())) == (200, {"settings": {"slowdown": True}})
    t0 = time.monotonic()
    assert dns.slow_down("10.0.0.5") and time.monotonic() - t0 >= 0.14
    assert j(app.route("GET", "/api/stats", b"", req()))[1]["adult"]["slowed"][0]["id"] == "10.0.0.5"
    assert Settings(cfg.data_dir).slowdown is True                      # survives a restart
    assert State(settings=Settings(cfg.data_dir)).settings.slowdown is True
    app.route("POST", "/api/settings", b'{"slowdown": false}', req())
    assert Settings(cfg.data_dir).slowdown is False
    t0 = time.monotonic()
    assert dns.slow_down("10.0.0.5") and time.monotonic() - t0 < 0.05


def test_adult_blocking_is_identical_with_the_toggle_on_and_off(rig, tmp_path):
    _, st, guard, dns, app = rig
    out = []
    for on in (False, True):
        st.settings.slowdown = on
        guard.penalty = PenaltyBox(90)
        guard.flags = FlagLog(str(tmp_path / ("f%d.json" % on)))
        reply = dns.handle_packet(dnsproto.build_query(BAD), "10.0.0.5")
        out.append((reply[-4:], guard.penalty.remaining("10.0.0.5") > 0, [f["domain"] for f in guard.flags.snapshot()], st.events[-1][3:6]))
        dns.forward = lambda p: (_ for _ in ()).throw(AssertionError("an adult name must never be forwarded"))
    assert out[0] == out[1] and out[0][0] == b"\x00\x00\x00\x00" and out[0][1] is True
