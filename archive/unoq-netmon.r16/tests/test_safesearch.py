import struct

from overheard import config, dnsproto, safesearch
from overheard.adult import AdultFilter, FlagLog, Guard, PenaltyBox
from overheard.blocklist import Blocklist
from overheard.dnsserver import DnsServer
from overheard.state import State


def guard():
    return Guard(AdultFilter(), PenaltyBox(90), FlagLog("/tmp/ov-test-flags.json"))


def fake_upstream(pkt):
    """Answers any A query with 216.239.38.120."""
    name, qtype, end = dnsproto.parse_question(pkt)
    return pkt[:2] + b"\x81\x80" + pkt[4:6] + b"\x00\x01\x00\x00\x00\x00" + pkt[12:end] + b"\xc0\x0c\x00\x01\x00\x01" + struct.pack("!I", 300) + b"\x00\x04" + bytes([216, 239, 38, 120])


def test_targets():
    assert safesearch.target("www.google.com") == "forcesafesearch.google.com"
    assert safesearch.target("WWW.Bing.com.") == "strict.bing.com"
    assert safesearch.target("www.youtube.com") is None
    assert safesearch.target("m.youtube.com") is None and safesearch.target("youtube.com") is None      # Restricted Mode is gone
    assert safesearch.target("maps.google.com") is None


def test_search_query_is_answered_with_cname_and_address():
    srv = DnsServer(config.parse([]), State(), Blocklist(), fake_upstream, guard())
    r = srv.handle_packet(dnsproto.build_query("www.google.com", txid=0x4242), "10.0.0.2")
    assert r[:2] == b"\x42\x42" and struct.unpack("!H", r[6:8])[0] == 2          # CNAME + one A
    assert b"forcesafesearch" in r and r.endswith(bytes([216, 239, 38, 120]))
    _, ips = dnsproto.process_reply(r, 30)
    assert ips == ["216.239.38.120"]


def test_aaaa_gets_an_empty_answer():
    srv = DnsServer(config.parse([]), State(), Blocklist(), fake_upstream, guard())
    r = srv.handle_packet(dnsproto.build_query("www.google.com", qtype=28), "10.0.0.2")
    assert struct.unpack("!H", r[6:8])[0] == 0


def test_upstream_failure_is_silent():
    def boom(p):
        raise OSError

    assert DnsServer(config.parse([]), State(), Blocklist(), boom, guard()).handle_packet(dnsproto.build_query("www.bing.com"), "10.0.0.2") is None
