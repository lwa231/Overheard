import struct

from overheard import config, dnsproto
from overheard.adult import AdultFilter, FlagLog, Guard, PenaltyBox
from overheard.blocklist import Blocklist
from overheard.dnsserver import DnsServer
from overheard.sampler import is_private, parse_ss
from overheard.services import classify
from overheard.state import State


def G():
    return Guard(AdultFilter(), PenaltyBox(90), FlagLog("/tmp/ov-test-flags.json"))



class Clock:
    def __init__(self, t=1_700_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_classify():
    assert classify("rr3---sn-x.googlevideo.com") == ("YouTube", "video")
    assert classify("www.google.com") == ("Google search", "search")
    assert classify("mail.google.com") == ("Google", "feed")
    assert classify("nothing.example.org") == ("Other", "other")


def test_blocklist_matches_parents():
    b = Blocklist({"doubleclick.net"})
    assert b.is_blocked("ads.doubleclick.net")
    assert not b.is_blocked("net")
    assert b.is_blocked("a.b.doubleclick.net")
    assert not b.is_blocked("example.com")


def test_parse_question_and_block_reply():
    pkt = dnsproto.build_query("ads.example.com")
    name, qtype, end = dnsproto.parse_question(pkt)
    assert (name, qtype) == ("ads.example.com", 1)
    r = dnsproto.blocked_reply(pkt, qtype, end)
    assert r[:2] == pkt[:2] and r[-4:] == b"\x00\x00\x00\x00"
    assert struct.unpack("!H", r[6:8])[0] == 1


def _answer(pkt, ttl, ip=b"\x01\x02\x03\x04"):
    return pkt[:2] + b"\x81\x80" + pkt[4:6] + b"\x00\x01\x00\x00\x00\x00" + pkt[12:] + b"\xc0\x0c\x00\x01\x00\x01" + struct.pack("!I", ttl) + b"\x00\x04" + ip


def test_process_reply_caps_ttl_and_extracts_ips():
    pkt = dnsproto.build_query("example.com")
    out, ips = dnsproto.process_reply(_answer(pkt, 3600), 30)
    assert ips == ["1.2.3.4"]
    assert struct.unpack("!I", out[-10:-6])[0] == 30


def test_state_dedupes_a_aaaa_https():
    c = Clock()
    s = State(c)
    assert s.record("10.0.0.2", "www.youtube.com", False)
    assert not s.record("10.0.0.2", "www.youtube.com", False)
    c.t += 2
    assert s.record("10.0.0.2", "www.youtube.com", False)
    assert s.dns["total"] == 2


def test_state_notifies_listeners():
    got = []
    s = State(Clock())
    s.listeners.append(lambda *a: got.append(a))
    s.record("10.0.0.2", "ads.x.com", True)
    assert got[0][1:] == ("10.0.0.2", "Ads and trackers", "ads", True)


def test_dns_server_blocks_and_forwards():
    cfg = config.parse(["--ttl", "30"])
    s = State(Clock())
    calls = []

    def fwd(pkt):
        calls.append(pkt)
        return _answer(pkt, 999)
    srv = DnsServer(cfg, s, Blocklist({"ads.com"}), fwd, G())
    blocked = srv.handle_packet(dnsproto.build_query("x.ads.com"), "10.0.0.2")
    assert blocked and not calls
    ok = srv.handle_packet(dnsproto.build_query("good.org"), "10.0.0.2")
    assert ok and len(calls) == 1 and s.ipmap["1.2.3.4"] == "good.org"
    assert s.dns["blocked"] == 1 and s.dns["total"] == 2


def test_dns_server_survives_garbage_and_upstream_failure():
    cfg = config.parse([])
    srv = DnsServer(cfg, State(Clock()), Blocklist(), lambda p: (_ for _ in ()).throw(OSError()), G())
    assert srv.handle_packet(b"\x00", "10.0.0.2") is None
    assert srv.handle_packet(dnsproto.build_query("good.org"), "10.0.0.2") is None


def test_private_addresses():
    assert is_private("192.168.1.5") and is_private("172.20.1.1") and is_private("100.69.41.76")
    assert not is_private("8.8.8.8") and not is_private("172.32.0.1")


def test_parse_ss():
    text = "ESTAB 0 0 192.168.1.9:5000 142.250.1.1:443\n\t cubic bytes_received:1000 x\nESTAB 0 0 192.168.1.9:5001 10.0.0.1:443\n\t bytes_received:5\n"
    cnt, agg = parse_ss(text)
    assert cnt == {"142.250.1.1": 1} and agg["142.250.1.1"] == 1000
