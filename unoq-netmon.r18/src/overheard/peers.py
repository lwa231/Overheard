"""Sites: a read-only summary of other Overheard boards (peers) reached over Tailscale.
Peers live in <data_dir>/peers.json (mode 600, it holds their access keys):
  {"site": "apartment", "peers": [{"name": "home", "url": "http://100.64.0.1:8080", "key": "<that board's access key>"}]}
A peer is a literal Tailscale address (100.64.0.0/10); names are not accepted. It is asked for its normal GET /api/stats with its
access key only, never an unlock session, so only its locked view crosses boards: no looked-up names. Whatever comes back is
rebuilt here from known keys before the dashboard sees it."""
import http.client
import ipaddress
import json
import os
import re
import socket
import threading
import time
from urllib.parse import urlparse

from . import auth
from .fingerprint import RULES
from .services import SERVICES

FILE = "peers.json"
MAX_PEERS, TIMEOUT, MAX_BYTES, MAX_FILE, CACHE_S = 8, 2.0, 256 * 1024, 64 * 1024, 2.0
NAME = re.compile(r"[a-z0-9-]{1,24}")
KEY = re.compile(r"[A-Za-z0-9_-]{8,128}")       # what auth.load_token makes; also keeps a header injection out of the Cookie line
TAILNET = ipaddress.ip_network("100.64.0.0/10")
# What a locked reply (stats.build_stats with full=False) may name. Everything else a peer sends is dropped.
SVC = set(SERVICES) | {"Everything else", "Ads and trackers", "Connection"}
LABELS = {r[0] for r in RULES} | {"Device", "This board", "Several devices (shared address)"}
UPSTREAM, CONF = {"tls", "plain", "mixed", "idle", "demo"}, {"high", "medium", "low", "none"}
IFACE = re.compile(r"[A-Za-z0-9_-]{1,16}")
SYS = ("cpu", "cores", "mem_used", "mem_total", "temp", "disk_used", "disk_total", "load", "uptime")


class Unreachable(Exception):
    """The peer is down, too slow, or sent something we do not accept."""


def default_site():
    """This board's own name when peers.json does not give one: its hostname, cleaned up."""
    return re.sub(r"[^a-z0-9-]", "-", socket.gethostname().lower().split(".")[0])[:24].strip("-") or "here"


def _base(url, loopback):
    """scheme://host[:port] of a peer, or ValueError. Outbound guard: the host is a literal Tailscale address (100.64.0.0/10), no names."""
    try:
        u = urlparse(url)
        host, port = u.hostname, u.port
    except (ValueError, AttributeError):
        raise ValueError("address not allowed") from None
    if (not isinstance(url, str) or u.scheme not in ("http", "https") or not host or u.username is not None or u.password is not None
            or u.path not in ("", "/") or u.params or u.query or u.fragment or (port is not None and not 1 <= port <= 65535)):
        raise ValueError("address not allowed")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise ValueError("address not allowed") from None
    if not (ip in TAILNET or (loopback and ip.is_loopback)):
        raise ValueError("address not allowed")
    return "%s://%s" % (u.scheme, u.netloc)


def _num(v, d=0):
    return v if type(v) in (int, float) and abs(v) < 1e15 else d          # not a bool, and finite (NaN fails the comparison)


def _in(v, ok, d=None):
    return v if isinstance(v, str) and v in ok else d


def _rx(v, rx):
    return v if isinstance(v, str) and rx.fullmatch(v) else ""


def _ip(v):
    try:
        return str(ipaddress.ip_address(v)) if isinstance(v, str) else ""
    except ValueError:
        return ""


def _id(v):
    """A device id is a literal IP address or the board's own fixed marker: nothing that could read as a hostname (a hex-and-dots check let `cafe.bad.de` through)."""
    ip = _ip(v)
    return v if v == "this board" else ip if ip and "%" not in ip else ""


def _dicts(v, n):
    return [x for x in v[:n] if isinstance(x, dict)] if isinstance(v, list) else []


def _row(r):
    s = _in(r.get("service"), SVC)
    return s and {"service": s, "v": [_num(x) for x in r["v"][:120]] if isinstance(r.get("v"), list) else [], **({"line": True} if r.get("line") is True else {})}


def _dev(v):
    rows = [x for x in map(_row, _dicts(v.get("rows"), 12)) if x]
    return _id(v.get("id")) and {
        "id": _id(v.get("id")), "label": _in(v.get("label"), LABELS, "Device"), "confidence": _in(v.get("confidence"), CONF, "none"), "evidence": [],
        "shared": v.get("shared") is True, "last": _num(v.get("last")), "lookups": _num(v.get("lookups")), "rate": _num(v.get("rate")),
        "now": _in(v.get("now"), SVC), "rows": rows}


def _locked(d):
    """Rebuild the locked view from known keys only, whatever the peer sent: mirrors stats.build_stats(full=False), so no looked-up
    name, free-form label, setting or unknown key can pass. ValueError when it does not look like a stats reply at all."""
    dn = d.get("dns")
    if not isinstance(dn, dict):
        raise ValueError("unexpected shape")
    ad, nt, sy = (d.get(k) if isinstance(d.get(k), dict) else {} for k in ("adult", "net", "sys"))
    net = {"iface": _rx(nt.get("iface"), IFACE), "gateway": _ip(nt.get("gateway")), "addr": _ip(nt.get("addr")), "wireless": nt.get("wireless") is True}
    sysv = {k: _num(sy[k], None) for k in SYS if k in sy}
    if isinstance(sy.get("cpu_hist"), list):
        sysv["cpu_hist"] = [_num(x) for x in sy["cpu_hist"][:60]]
    return {
        "host": "", "demo": d.get("demo") is True, "uptime": _num(d.get("uptime")), "t0": _num(d.get("t0")), "step": _num(d.get("step"), 5),
        "dns": {"enabled": dn.get("enabled") is True, "total": _num(dn.get("total")), "blocked": _num(dn.get("blocked")), "clients": _num(dn.get("clients")),
                "upstream": _in(dn.get("upstream"), UPSTREAM, "idle")},
        "adult": {"enabled": ad.get("enabled") is True, "slowed": [], "flagged": 0, "listed": 0},
        "now": {"service": None, "mode": None, "window": 45, "evidence": []},
        "devices": [x for x in map(_dev, _dicts(d.get("devices"), 64)) if x],
        "rx": _num(d.get("rx")), "tx": _num(d.get("tx")), "recent": [],
        "conns": [{"ip": _ip(c.get("ip")), "service": _in(c.get("service"), SVC, "Other"), "count": _num(c.get("count")), "bytes": _num(c.get("bytes"))}
                  for c in _dicts(d.get("conns"), 6)],
        "refused": [], "net": {k: v for k, v in net.items() if v}, "sys": sysv, "unlocked": False}


def _get(p, timeout):
    """GET /api/stats. The whole exchange has a hard wall-clock limit (2 x timeout): a watchdog cuts the socket, so a peer that drips
    bytes (headers or body) cannot hold a thread or the peer's lock. No redirects are followed and no proxy is used."""
    u = urlparse(p.base)
    conn = (http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection)(u.hostname, u.port, timeout=timeout)
    cut = []

    def kill():
        cut.append(1)
        try:
            conn.sock.shutdown(socket.SHUT_RDWR)
        except (AttributeError, OSError):
            pass
    dog = threading.Timer(2 * timeout, kill)
    dog.daemon = True
    dog.start()
    try:
        conn.request("GET", "/api/stats", headers={"Cookie": "%s=%s" % (auth.COOKIE, p.key), "Accept": "application/json", "User-Agent": "overheard-sites"})
        r = conn.getresponse()
        if r.status != 200:
            raise ValueError("status")
        buf = r.read(MAX_BYTES + 1)
    finally:
        dog.cancel()
        conn.close()
    if cut:
        raise ValueError("too slow")
    if len(buf) > MAX_BYTES:
        raise ValueError("too big")
    d = json.loads(buf)
    if not isinstance(d, dict):
        raise ValueError("not an object")
    return _locked(d)


class _Peer:
    def __init__(self, name, base, key):
        self.name, self.base, self.key = name, base, key
        self.lock = threading.Lock()
        self.data = self.at = self.tried = self.ok = None      # last good reply, when, last attempt, did it work


class Peers:
    def __init__(self, site, peers, clock=time.monotonic, timeout=TIMEOUT):
        self.site, self.clock, self.timeout = site, clock, timeout
        self._p = {p.name: p for p in peers}

    def summary(self):
        """Names and state only: never an address or a key."""
        now = self.clock()
        return {"site": self.site, "sites": [{"name": self.site, "self": True}] + [
            {"name": p.name, "self": False, "ok": p.ok, "age": None if p.at is None else round(now - p.at, 1)} for p in self._p.values()]}

    def fetch(self, name):
        """The peer's locked stats plus "site". KeyError: no such peer. Unreachable: it did not answer well."""
        p = self._p[name]
        if (p.tried is None or self.clock() - p.tried >= CACHE_S) and p.lock.acquire(blocking=False):   # one asker at a time per peer
            try:
                p.tried = self.clock()
                try:
                    p.data, p.ok = _get(p, self.timeout), True
                    p.at = p.tried
                except (OSError, ValueError, http.client.HTTPException, RecursionError):
                    p.ok = False
            finally:
                p.lock.release()
        if not p.ok:
            raise Unreachable(name)
        return {**p.data, "site": p.name}


def load(data_dir, loopback=False, clock=time.monotonic, timeout=TIMEOUT, log=print):
    """Peers from <data_dir>/peers.json, or None (feature off) when it is missing, empty or not usable. Never raises.
    `loopback` exists for tests only."""
    path = os.path.join(data_dir, FILE)
    try:
        st = os.stat(path)
    except OSError:
        return None
    try:
        if os.name == "posix" and st.st_mode & 0o077:
            raise ValueError("it holds access keys, so it must not be readable by others (chmod 600)")
        with open(path, encoding="utf-8") as f:
            raw = f.read(MAX_FILE + 1)
        if len(raw) > MAX_FILE:
            raise ValueError("file too big")
        return _parse(json.loads(raw), loopback, clock, timeout)
    except (OSError, ValueError, RecursionError) as e:
        log("peers.json ignored: %s" % (e if isinstance(e, ValueError) and not isinstance(e, json.JSONDecodeError) else "not usable"))
        return None


def _parse(doc, loopback, clock, timeout):
    items = doc.get("peers") if isinstance(doc, dict) else None
    if not isinstance(items, list):
        raise ValueError('expected {"site": ..., "peers": [...]}')
    if not items:
        return None
    if len(items) > MAX_PEERS:
        raise ValueError("more than %d peers" % MAX_PEERS)
    site = doc.get("site", default_site())
    if not isinstance(site, str) or not NAME.fullmatch(site):
        raise ValueError("bad site name")
    seen, out = {site}, []
    for i, it in enumerate(items, 1):
        name, key = (it.get("name"), it.get("key")) if isinstance(it, dict) else (None, None)
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise ValueError("peer %d: bad name" % i)
        if name in seen:
            raise ValueError("peer %d: name repeats or is this board's own" % i)
        if not isinstance(key, str) or not KEY.fullmatch(key):
            raise ValueError("peer %d: bad key" % i)
        try:
            base = _base(it.get("url"), loopback)
        except ValueError as e:
            raise ValueError("peer %d: %s" % (i, e)) from None
        seen.add(name)
        out.append(_Peer(name, base, key))
    return Peers(site, out, clock, timeout)
