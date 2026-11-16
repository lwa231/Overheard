"""r16: the adult guard stays hard-coded, the slowdown is a persisted toggle."""
import dataclasses
import json
import time

import pytest

from overheard import adult, config, dnsproto
from overheard.adult import AdultFilter, FlagLog, Guard, PenaltyBox
from overheard.blocklist import Blocklist
from overheard.dnsserver import DnsServer
from overheard.settings import Settings
from overheard.state import State

NEVER = ["youtube.com", "www.youtube.com", "googlevideo.com", "rr3---sn-p5qs7nsd.googlevideo.com", "i.ytimg.com", "reddit.com", "twitch.tv",
         "apple.com", "microsoft.com", "github.com", "en.wikipedia.org", "essex.gov.uk", "sussex.ac.uk", "pornichet.fr", "sex.ed.gov"]


@pytest.mark.parametrize("name", NEVER)
def test_common_sites_are_never_flagged(name):
    assert AdultFilter().check(name) is None


@pytest.mark.parametrize("name", ["pornhub.com", "www.xvideos.com", "xnxx.example", "x.hentai-site.net", "foo.xxx", "chaturbate.com", "cdn.xhamster.org"])
def test_obviously_explicit_names_are_flagged(name):
    assert AdultFilter().check(name) == "heuristic"


def test_corrupt_or_empty_adult_file_cannot_weaken_the_guard(tmp_path, monkeypatch):
    def offline(url, timeout=0):
        raise OSError("offline")
    monkeypatch.setattr(adult.urllib.request, "urlopen", offline)
    for blob in (b"", b"\xff\xfe\x00garbage\x80\x81", b"{not a list", b"com\nlocalhost\n0.0.0.0\n"):
        (tmp_path / "adult.txt").write_bytes(blob)
        f = AdultFilter.load(str(tmp_path), log=lambda m: None)
        assert f.check("pornhub.com") == "heuristic" and f.check("foo.xxx") == "heuristic" and f.check("example.org") is None


def test_adult_file_keeps_good_lines_and_drops_junk(tmp_path):
    (tmp_path / "adult.txt").write_bytes(b"bad.example\n\xff\xfe junk line\nnodot\n" + b"\n".join(b"d%d.example" % i for i in range(adult.MIN_LIST)))
    f = AdultFilter.load(str(tmp_path), log=lambda m: None)
    assert f.check("www.bad.example") == "list" and "nodot" not in f.domains


def test_settings_default_off_persist_and_survive_corruption(tmp_path):
    s = Settings(str(tmp_path))
    assert s.slowdown is False
    s.slowdown = True
    assert s.slowdown is True and json.loads((tmp_path / "settings.json").read_text()) == {"slowdown": True}
    assert not (tmp_path / "settings.json.tmp").exists()
    assert Settings(str(tmp_path)).slowdown is True
    s.slowdown = False
    assert Settings(str(tmp_path)).slowdown is False
    for blob in (b"", b"\xff\x00garbage", b"[1]", b'{"slowdown": "yes"}', b'{"slowdown": 1}', b"null"):
        (tmp_path / "settings.json").write_bytes(blob)
        assert Settings(str(tmp_path)).slowdown is False


def test_state_exposes_settings():
    assert State().settings.slowdown is False
    s = Settings()
    assert State(settings=s).settings is s


def test_slowdown_toggle_controls_delay_but_never_blocking(tmp_path):
    cfg = dataclasses.replace(config.parse([]), penalty_delay=0.15)
    guard = Guard(AdultFilter({"badsite.com"}), PenaltyBox(90), FlagLog(str(tmp_path / "f.json")))
    st = State()
    srv = DnsServer(cfg, st, Blocklist(), lambda p: p, guard)
    r = srv.handle_packet(dnsproto.build_query("www.badsite.com"), "10.0.0.5")
    assert r[-4:] == b"\x00\x00\x00\x00"                               # blocked with the toggle off ...
    t0 = time.monotonic()
    assert srv.slow_down("10.0.0.5") and time.monotonic() - t0 < 0.05
    assert guard.summary()["slowed"] == [] and guard.summary()["slowdown"] is False
    st.settings.slowdown = True                                         # ... and with it on
    assert srv.handle_packet(dnsproto.build_query("www.badsite.com"), "10.0.0.5")[-4:] == b"\x00\x00\x00\x00"
    assert guard.summary()["slowdown"] is True and guard.summary()["slowed"][0]["id"] == "10.0.0.5"
    t0 = time.monotonic()
    assert srv.slow_down("10.0.0.5") and time.monotonic() - t0 >= 0.14
