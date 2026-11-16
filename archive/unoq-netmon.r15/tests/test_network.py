"""Real sockets on loopback: UDP and TCP DNS end to end, plus random-input fuzzing of the parser."""
import dataclasses
import random
import socket
import struct
import time

import pytest

from overheard import config, dnsproto
from overheard.adult import AdultFilter, FlagLog, Guard, PenaltyBox
from overheard.blocklist import Blocklist
from overheard.dnsserver import DnsServer
from overheard.state import State


def upstream(pkt):
    name, qtype, end = dnsproto.parse_question(pkt)
    return pkt[:2] + b"\x81\x80" + pkt[4:6] + b"\x00\x01\x00\x00\x00\x00" + pkt[12:end] + b"\xc0\x0c\x00\x01\x00\x01" + struct.pack("!I", 300) + b"\x00\x04" + bytes([1, 2, 3, 4])


@pytest.fixture
def dns(tmp_path):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    cfg = dataclasses.replace(config.parse(["--bind", "127.0.0.1", "--dns-port", str(port)]), penalty_delay=0.3)
    guard = Guard(AdultFilter({"bad.example"}), PenaltyBox(90), FlagLog(str(tmp_path / "f.json")))
    srv = DnsServer(cfg, State(), Blocklist({"ads.example"}), upstream, guard)
    assert srv.start() is None, srv.error
    return srv, port, guard


def udp(port, name, timeout=2.0):
    c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    c.settimeout(timeout)
    c.sendto(dnsproto.build_query(name), ("127.0.0.1", port))
    try:
        return c.recvfrom(4096)[0]
    except TimeoutError:
        return None
    finally:
        c.close()


def test_udp_forward_block_and_adult(dns):
    _, port, guard = dns
    assert dnsproto.process_reply(udp(port, "fine.example"), 0)[1] == ["1.2.3.4"]
    assert udp(port, "ads.example")[-4:] == b"\x00\x00\x00\x00"
    assert udp(port, "bad.example", timeout=3)[-4:] == b"\x00\x00\x00\x00"
    assert guard.penalty.remaining("127.0.0.1") > 0


def test_tcp_dns(dns):
    _, port, _ = dns
    q = dnsproto.build_query("fine.example")
    with socket.create_connection(("127.0.0.1", port), timeout=3) as c:
        c.sendall(struct.pack("!H", len(q)) + q)
        n = struct.unpack("!H", c.recv(2, socket.MSG_WAITALL))[0]
        assert dnsproto.process_reply(c.recv(n, socket.MSG_WAITALL), 0)[1] == ["1.2.3.4"]


def test_slowed_device_really_waits(dns):
    _, port, guard = dns
    guard.penalty.trip("127.0.0.1")
    t0 = time.monotonic()
    assert udp(port, "fine.example", timeout=3) is not None
    assert time.monotonic() - t0 >= 0.25


def test_tcp_garbage_does_not_kill_the_listener(dns):
    _, port, _ = dns
    for payload in (b"", b"\x00", b"\xff\xff" + b"x" * 10, struct.pack("!H", 5000) + b"short"):
        with socket.create_connection(("127.0.0.1", port), timeout=2) as c:
            c.sendall(payload)
    assert udp(port, "fine.example") is not None


def test_parser_survives_random_and_mutated_packets():
    rng = random.Random(7)
    base = dnsproto.build_query("www.example.com")
    for _ in range(4000):
        b = bytearray(base)
        for _ in range(rng.randint(1, 6)):
            b[rng.randrange(len(b))] = rng.randrange(256)
        pkt = bytes(b[:rng.randint(0, len(b))]) if rng.random() < .3 else bytes(b)
        try:
            dnsproto.parse_question(pkt)
        except dnsproto.BadPacket:
            pass
    for _ in range(2000):
        try:
            dnsproto.parse_question(bytes(rng.randrange(256) for _ in range(rng.randint(0, 80))))
        except dnsproto.BadPacket:
            pass
    for _ in range(2000):                                  # reply processing must never raise either
        dnsproto.process_reply(bytes(rng.randrange(256) for _ in range(rng.randint(0, 120))), 30)


def test_refused_sources_are_counted_and_bounded(tmp_path):
    from overheard import state as st
    from overheard.stats import build_stats
    cfg = config.parse(["--allow", "10.0.0.0/8"])
    guard = Guard(AdultFilter(set()), PenaltyBox(90), FlagLog(str(tmp_path / "f.json")))
    s = State()
    srv = DnsServer(cfg, s, Blocklist(set()), upstream, guard)
    q = dnsproto.build_query("example.com")
    assert srv.handle_packet(q, "203.0.113.254") is None and srv.handle_packet(q, "203.0.113.254") is None
    assert srv.handle_packet(q, "10.1.2.3") is not None
    assert s.refused["203.0.113.254"][0] == 2 and "10.1.2.3" not in s.refused
    out = build_stats(s, cfg, guard)
    assert out["refused"][0]["id"] == "203.0.113.254" and out["refused"][0]["count"] == 2 and out["net"] == {}
    for i in range(st.REFUSED_MAX + 20):
        s.note_refused("203.0.113.%d" % (i % 250) if i < 250 else "x")
    assert len(s.refused) <= st.REFUSED_MAX
