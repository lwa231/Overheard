"""The DNS listener (UDP and TCP). handle_packet is pure enough to test without a socket."""
import ipaddress
import socket
import struct
import threading
import time

from . import safesearch
from .dnsproto import BadPacket, blocked_reply, build_query, formerr, parse_question, process_reply, truncated_reply

MAX_INFLIGHT = 64     # concurrent UDP queries; beyond this new ones are dropped (clients retry)
UDP_MAX = 1232        # larger answers are truncated so the client retries over TCP
TCP_SLOTS, TCP_PER_CLIENT, TCP_LIFETIME, TCP_QUERIES = 16, 4, 20.0, 20


def _recv_exact(conn, n, deadline=None):
    """Read exactly n bytes (TCP delivers pieces); None if the peer closes early or the deadline passes (drip-feeding)."""
    buf = b""
    while len(buf) < n:
        if deadline is not None and time.monotonic() > deadline:
            return None
        chunk = conn.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


class DnsServer:
    def __init__(self, cfg, state, blocklist, forward, guard):
        self.cfg, self.state, self.blocklist, self.forward, self.guard = cfg, state, blocklist, forward, guard
        if getattr(guard, "settings", None) is None:
            guard.settings = state.settings                 # so the guard's summary never reports a slowdown that is switched off
        self._slow_slots = threading.BoundedSemaphore(16)   # slowed queries wait here, never in the main pool
        self._slots = threading.BoundedSemaphore(MAX_INFLIGHT)
        self._tcp_slots = threading.BoundedSemaphore(TCP_SLOTS)
        self._tcp_per = {}
        self._noted = set()
        self.ready, self.error = threading.Event(), None
        self._nets = [ipaddress.ip_network(n) for n in cfg.allow]
        self._buckets = {}          # client -> (tokens, last)
        self._rl = threading.Lock()

    def permitted(self, ip):
        """Only answer clients in the allowed networks (never act as an open resolver) and within the rate limit."""
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if not any(addr in n for n in self._nets):
            self.state.note_refused(ip)
            self._note(ip, "refused: address is outside the allowed networks (%s)" % ", ".join(self.cfg.allow))
            return False
        now = time.monotonic()
        burst = max(1, self.cfg.rate) * 2
        with self._rl:
            tokens, last = self._buckets.get(ip, (burst, now))
            tokens = min(burst, tokens + (now - last) * self.cfg.rate)
            if len(self._buckets) > 2000:
                self._buckets.pop(next(iter(self._buckets)))
            if tokens < 1:
                self._buckets[ip] = (tokens, now)
                return False
            self._buckets[ip] = (tokens - 1, now)
            return True

    def _note(self, ip, text):
        """Print one line the first time a device does something noteworthy, so the service log shows who is (not) getting through."""
        with self._rl:
            if ip in self._noted or len(self._noted) > 500:
                return
            self._noted.add(ip)
        print("dns: %s %s" % (ip, text), flush=True)

    def handle_packet(self, pkt, client_ip):
        """Return the reply bytes for one query, or None to stay silent."""
        if not self.permitted(client_ip):
            return None
        self._note(client_ip, "first lookup received")
        try:
            name, qtype, end = parse_question(pkt)
        except BadPacket:
            return formerr(pkt) if len(pkt) >= 12 and not pkt[2] & 0x80 else None     # never answer a response: that could loop
        if self.guard.hit(client_ip, name):
            self.state.record(client_ip, name, True, adult=True)
            return blocked_reply(pkt, qtype, end)
        blocked = self.blocklist.is_blocked(name)
        self.state.record(client_ip, name, blocked)
        if blocked:
            return blocked_reply(pkt, qtype, end)
        tgt = safesearch.target(name)
        if tgt:
            return self._safe_search_reply(pkt, end, qtype, tgt)
        try:
            data, ips = process_reply(self.forward(pkt), self.cfg.ttl)
        except Exception:
            return None
        self.state.remember_ips(ips, name)
        return data

    def _safe_search_reply(self, pkt, end, qtype, tgt):
        ips = []
        if qtype == 1:
            try:
                _, ips = process_reply(self.forward(build_query(tgt, 1, int.from_bytes(pkt[:2], "big"))), self.cfg.ttl)
            except Exception:
                return None
            if not ips:
                return None
        return safesearch.build_reply(pkt, end, qtype, tgt, ips)

    def slow_down(self, client_ip):
        """Hold a reply for a device in the penalty box, if the slowdown setting is on. Returns False if the reply should be dropped instead."""
        if not self.state.settings.slowdown:
            return True
        left = self.guard.penalty.remaining(client_ip)
        if not left:
            return True
        if not self._slow_slots.acquire(blocking=False):
            return False                     # too many slowed queries waiting: drop, never starve other devices
        try:
            time.sleep(min(self.cfg.penalty_delay, left))
        finally:
            self._slow_slots.release()
        return True

    # ----- UDP -----
    def _udp_one(self, sock, pkt, addr):
        try:
            reply = self.handle_packet(pkt, addr[0])
            if reply and len(reply) > UDP_MAX:
                reply = truncated_reply(reply)          # tell the client to retry over TCP
            if reply and self.slow_down(addr[0]):
                sock.sendto(reply, addr)
        except OSError:
            pass
        finally:
            self._slots.release()

    def serve_udp(self, s):
        self.state.dns["enabled"] = True
        while True:
            try:
                pkt, addr = s.recvfrom(4096)
            except OSError:
                continue
            if self._slots.acquire(blocking=False):
                threading.Thread(target=self._udp_one, args=(s, pkt, addr), daemon=True).start()

    # ----- TCP (clients retry here when a UDP answer was too big) -----
    def _tcp_one(self, conn, addr):
        ip = addr[0]
        try:
            conn.settimeout(5)
            deadline = time.monotonic() + TCP_LIFETIME
            for _ in range(TCP_QUERIES):
                if time.monotonic() > deadline:
                    return
                head = _recv_exact(conn, 2, deadline)
                if head is None:
                    return
                n = struct.unpack("!H", head)[0]
                pkt = _recv_exact(conn, n, deadline) if n else b""
                reply = self.handle_packet(pkt, ip) if pkt is not None else None
                if reply is None or not self.slow_down(ip):
                    return
                conn.sendall(struct.pack("!H", len(reply)) + reply)
        except OSError:
            pass
        finally:
            conn.close()
            self._tcp_done(ip)

    def _tcp_done(self, ip):
        with self._rl:
            self._tcp_per[ip] = self._tcp_per.get(ip, 1) - 1
            if self._tcp_per[ip] <= 0:
                del self._tcp_per[ip]
        self._tcp_slots.release()

    def serve_tcp(self, s):
        while True:
            try:
                conn, addr = s.accept()
            except OSError:
                continue
            ip = addr[0]
            with self._rl:
                room = self._tcp_per.get(ip, 0) < TCP_PER_CLIENT
                if room:
                    self._tcp_per[ip] = self._tcp_per.get(ip, 0) + 1
            if not room:
                conn.close()
                continue
            if not self.permitted(ip) or not self._tcp_slots.acquire(blocking=False):
                conn.close()
                with self._rl:
                    self._tcp_per[ip] -= 1
                    if self._tcp_per[ip] <= 0:
                        del self._tcp_per[ip]
                continue
            threading.Thread(target=self._tcp_one, args=(conn, addr), daemon=True).start()

    def _bind(self):
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        t = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        t.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            u.bind((self.cfg.bind, self.cfg.dns_port))
            t.bind((self.cfg.bind, self.cfg.dns_port))
            t.listen(32)
        except OSError:
            u.close()
            t.close()
            raise
        return u, t

    def serve_forever(self):
        try:
            u, t = self._bind()
        except OSError as e:
            self.error = e
            self.ready.set()
            return
        self.ready.set()
        threading.Thread(target=self.serve_tcp, args=(t,), daemon=True).start()
        self.serve_udp(u)

    def start(self, timeout=5.0):
        """Run in the background; returns None once it is listening, or the error that stopped it."""
        threading.Thread(target=self.serve_forever, daemon=True).start()
        self.ready.wait(timeout)
        return self.error
