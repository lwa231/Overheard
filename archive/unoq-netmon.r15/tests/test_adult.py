import dataclasses
import time

import pytest

from overheard import config, dnsproto
from overheard.adult import AdultFilter, FlagLog, Guard, PenaltyBox, parse_list
from overheard.blocklist import Blocklist
from overheard.dnsserver import DnsServer
from overheard.profiles import categorize
from overheard.state import State


def mk(**kw):
    return AdultFilter({"badsite.com", "other.net"}, **kw)


def test_parse_list_handles_hosts_and_plain_formats():
    got = parse_list("# comment\n0.0.0.0 0.0.0.0\n0.0.0.0 a.example.com # note\n127.0.0.1 localhost\nplain.example.org\nnot a domain line\n")
    assert got == {"a.example.com", "plain.example.org"}


def test_list_hits_cover_subdomains_and_case():
    f = mk()
    assert f.check("badsite.com") == "list" and f.check("WWW.BadSite.com.") == "list" and f.check("a.b.other.net") == "list"
    assert f.check("goodsite.com") is None


@pytest.mark.parametrize("name,expect", [
    ("something.xxx", "heuristic"), ("www.sex", "heuristic"), ("cdn.pornexample.org", "heuristic"), ("sex.example.com", "heuristic"),
    ("sussex.ac.uk", None), ("essex.gov.uk", None), ("middlesex.edu", None), ("www.scunthorpe.co.uk", None),
    ("www.google.com", None), ("sextant-maps.com", None), ("pornography-studies.ac.uk", "heuristic")])
def test_heuristic_avoids_common_false_positives(name, expect):
    assert mk().check(name) == expect


def test_no_user_exceptions_exist():
    f = AdultFilter({"badsite.com"})
    assert f.check("badsite.com") == "list"
    assert not hasattr(f, "allow")


def test_penalty_box_expires_and_is_per_device():
    t = [100.0]
    box = PenaltyBox(90, clock=lambda: t[0])
    box.trip("a")
    assert box.remaining("a") == 90 and box.remaining("b") == 0
    t[0] += 60
    assert 29 <= box.remaining("a") <= 31
    box.trip("a")                                      # another adult lookup extends it
    t[0] += 89
    assert box.remaining("a") > 0
    t[0] += 2
    assert box.remaining("a") == 0 and box.active() == []


def test_flag_log_counts_persists_and_is_bounded(tmp_path):
    clock = [1000]
    log = FlagLog(str(tmp_path / "f.json"), clock=lambda: clock[0])
    log.add("Bad.com.", "list")
    clock[0] += 5
    log.add("bad.com", "list")
    snap = log.snapshot()
    assert snap == [{"domain": "bad.com", "hits": 2, "reason": "list", "first": 1000, "last": 1005}]
    log.save()
    assert FlagLog(str(tmp_path / "f.json")).snapshot()[0]["hits"] == 2
    assert "client" not in snap[0] and "device" not in snap[0]


def server(tmp_path, delay=0.0, **cfgargs):
    cfg = dataclasses.replace(config.parse([]), penalty_delay=delay)
    guard = Guard(mk(), PenaltyBox(90), FlagLog(str(tmp_path / "f.json")))
    st = State()
    return DnsServer(cfg, st, Blocklist(), lambda p: p, guard), st, guard


def test_adult_lookup_is_refused_logged_and_trips_only_that_device(tmp_path):
    srv, st, guard = server(tmp_path)
    reply = srv.handle_packet(dnsproto.build_query("www.badsite.com"), "10.0.0.5")
    assert reply and reply[-4:] == b"\x00\x00\x00\x00"           # 0.0.0.0
    assert guard.penalty.remaining("10.0.0.5") > 0 and guard.penalty.remaining("10.0.0.6") == 0
    assert guard.flags.snapshot()[0]["domain"] == "www.badsite.com"
    ev = st.events[-1]
    assert ev[3] == "Adult content" and ev[5] is True


def test_slowdown_applies_only_to_the_tripped_device_and_ends(tmp_path):
    srv, _, guard = server(tmp_path, delay=0.15)
    guard.penalty.trip("10.0.0.5")
    t0 = time.monotonic()
    assert srv.slow_down("10.0.0.6") and time.monotonic() - t0 < 0.05
    t0 = time.monotonic()
    assert srv.slow_down("10.0.0.5") and time.monotonic() - t0 >= 0.14
    guard.penalty.until["10.0.0.5"] = time.monotonic() - 1
    t0 = time.monotonic()
    assert srv.slow_down("10.0.0.5") and time.monotonic() - t0 < 0.05


def test_slowed_queries_are_dropped_not_queued_forever(tmp_path):
    srv, _, guard = server(tmp_path, delay=0.01)
    guard.penalty.trip("10.0.0.5")
    held = [srv._slow_slots.acquire(blocking=False) for _ in range(16)]
    assert all(held)
    assert srv.slow_down("10.0.0.5") is False            # pool exhausted: drop
    assert srv.slow_down("10.0.0.6") is True              # other devices unaffected


def test_adult_is_never_profiled():
    assert categorize("Adult content", "adult", True) is None


def test_stats_and_flagged_endpoint(tmp_path):
    import json

    from overheard.server import App
    srv, st, guard = server(tmp_path)
    srv.handle_packet(dnsproto.build_query("x.badsite.com"), "10.0.0.5")
    app = App(config.parse([]), st, guard=guard)
    s = json.loads(app.route("GET", "/api/stats")[2])
    assert s["adult"]["slowed"][0]["id"] == "10.0.0.5" and s["adult"]["flagged"] == 1
    assert s["now"]["service"] is None                    # adult traffic is never "what is playing"
    f = json.loads(app.route("GET", "/api/flagged")[2])
    assert f["items"][0]["domain"] == "x.badsite.com"


def test_nothing_can_switch_the_filters_off_or_weaken_them():
    import io
    import contextlib
    for flag in ("--no-adult-filter", "--no-safesearch", "--penalty-seconds", "--penalty-delay", "--adult-allow"):
        with contextlib.redirect_stderr(io.StringIO()), pytest.raises(SystemExit):
            config.parse([flag] if not flag.startswith("--penalty") else [flag, "0"])
    cfg = config.parse([])
    assert not hasattr(cfg, "adult_filter") and not hasattr(cfg, "safesearch")




def test_background_infrastructure_is_never_flagged_even_if_a_list_mentions_it():
    f = AdultFilter({"securemetrics.apple.com", "gemini.yahoo.com", "d111abc.cloudfront.net", "realporn.example"})
    for n in ("securemetrics.apple.com", "gemini.yahoo.com", "d111abc.cloudfront.net", "x.apple.com"):
        assert f.check(n) is None
    assert f.check("realporn.example") == "list"
