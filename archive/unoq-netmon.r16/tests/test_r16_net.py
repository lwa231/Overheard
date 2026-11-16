"""r16: safe defaults, upstream that cannot hang on a blocked port 853, and the phone test verdicts."""
import json
import os
import socket
import subprocess
import threading
import time

from overheard import config, dnsproto, doctor
from overheard import upstream as up
from overheard.upstream import Forwarder

ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_no_personal_address_in_code_defaults():
    assert not any(x.startswith("68.") for x in config.Config.allow)
    assert config.parse(["--allow-extra", "203.0.113.7/32"]).allow == config.Config.allow + ("203.0.113.7/32",)


def test_installer_has_no_insecure_defaults():
    for f in ("scripts/install.sh", "Install Overheard.command"):
        text = open(os.path.join(ROOT, f)).read()
        assert "68.180" not in text and 'NO_TLS="${NO_TLS:-1}"' not in text
    for f in ("scripts/install.sh", "scripts/status.sh", "Check Overheard.command", "Install Overheard.command", "Phone Test.command"):
        assert subprocess.run(["bash", "-n", os.path.join(ROOT, f)]).returncode == 0


def _udp_echo():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))

    def run():
        pkt, addr = sock.recvfrom(4096)
        sock.sendto(pkt[:2] + b"\x81\x80" + pkt[4:], addr)
    threading.Thread(target=run, daemon=True).start()
    return sock.getsockname()[1]


def test_blocked_dot_port_falls_back_to_udp_fast_and_is_not_retried(monkeypatch):
    timeouts = []

    def blocked(addr, timeout=None):
        timeouts.append(timeout)
        time.sleep(timeout)                    # a dropped SYN: nothing happens until the timeout
        raise TimeoutError("port 853 blocked")
    monkeypatch.setattr(up.socket, "create_connection", blocked)
    port = _udp_echo()
    counters = {"tls": 0, "plain": 0}
    f = Forwarder(config.parse(["--upstream", "127.0.0.1", "--upstream-port", str(port)]), counters)
    q = dnsproto.build_query("ok.org", txid=0x4242)
    t = time.monotonic()
    assert f(q)[:2] == q[:2]
    assert time.monotonic() - t < 2.5          # one short connect attempt, then UDP
    assert timeouts == [up.CONNECT_S] and up.CONNECT_S <= 2
    assert counters == {"tls": 0, "plain": 1}
    f._plain = lambda pkt: b"again"
    t = time.monotonic()
    assert f(q) == b"again" and time.monotonic() - t < 0.2 and len(timeouts) == 1     # circuit breaker: no new connect


def _stats(recent=(), refused=()):
    return {"recent": [{"t": t, "client": c, "domain": d, "service": "x", "blocked": False} for t, c, d in recent],
            "refused": [{"id": i, "count": n, "last": 0} for i, n in refused]}


def test_phone_test_verdicts():
    d = doctor.DOMAIN
    assert doctor.verdict(_stats([(10, "192.168.1.7", d + ".")]), d, 5, {}) == ("192.168.1.7", [])
    assert doctor.verdict(_stats([(3, "192.168.1.7", d)]), d, 5, {}) == (None, [])            # older than the test
    assert doctor.verdict(_stats([(10, "192.168.1.7", "other.org")]), d, 5, {}) == (None, [])
    assert doctor.verdict(_stats(refused=[("68.1.2.3", 4), ("9.9.9.9", 2)]), d, 5, {"9.9.9.9": 2}) == (None, ["68.1.2.3"])


def _run(payloads):
    out, it, now = [], iter(payloads), [0.0]
    seen = []
    import urllib.request as ur
    orig = ur.urlopen

    class R:
        def __init__(self, p): self.p = p
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, *a): return json.dumps(self.p).encode()
    last = [None]

    def fake(req, timeout=None):
        seen.append(req.headers)
        try:
            last[0] = next(it)
        except StopIteration:
            pass
        return R(last[0])
    ur.urlopen = fake
    try:
        def sleep(s): now[0] += s
        code = doctor.run("http://x/api/stats", "tok", doctor.DOMAIN, 5, say=out.append, sleep=sleep, clock=lambda: now[0])
    finally:
        ur.urlopen = orig
    return code, "\n".join(out), seen


def test_phone_test_reports_and_sends_token_and_doctor_header():
    d = doctor.DOMAIN
    code, text, seen = _run([_stats(), _stats(), _stats([(1.0, "192.168.1.7", d)])])
    assert code == 0 and "ANSWERED from 192.168.1.7" in text
    assert seen[0]["Cookie"] == "ov=tok" and seen[0]["X-overheard-doctor"] == "1"
    code, text, _ = _run([_stats(), _stats(refused=[("68.1.2.3", 1)])])
    assert code == 1 and "REFUSED from 68.1.2.3" in text and "ALLOW_EXTRA=68.1.2.3/32" in text
    code, text, _ = _run([_stats()])
    assert code == 1 and "NEVER ARRIVED" in text
