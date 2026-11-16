"""Forward lookups upstream: DNS over TLS first, plain UDP as the fallback."""
import queue
import socket
import time
import ssl
import struct

DOT_RETRY_S = 60.0


def _recvn(sock, n):
    b = b""
    while len(b) < n:
        c = sock.recv(n - len(b))
        if not c:
            raise ConnectionError("closed")
        b += c
    return b


class Forwarder:
    def __init__(self, cfg, counters):
        self.cfg = cfg
        self.counters = counters      # dict with "tls" and "plain"
        self.pool = queue.LifoQueue(maxsize=4)
        self._ctx = None
        self._dot_down_until = 0.0     # after a TLS failure, go straight to plain UDP for a while so lookups do not each wait for the timeout
        self.clock = time.monotonic

    def _connect(self):
        c = self.cfg
        if self._ctx is None:
            self._ctx = ssl.create_default_context(cafile=c.tls_cafile) if c.tls_cafile else ssl.create_default_context()
        s = socket.create_connection((c.upstream, c.tls_port), timeout=3)
        return self._ctx.wrap_socket(s, server_hostname=c.tls_name)

    def _dot(self, pkt):
        for attempt in (0, 1):
            try:
                conn = self.pool.get_nowait() if attempt == 0 else self._connect()
            except queue.Empty:
                conn = self._connect()
            try:
                conn.settimeout(3)
                conn.sendall(struct.pack("!H", len(pkt)) + pkt)
                resp = _recvn(conn, struct.unpack("!H", _recvn(conn, 2))[0])
                if resp[:2] != pkt[:2]:
                    raise ConnectionError("id mismatch")
                try:
                    self.pool.put_nowait(conn)
                except queue.Full:
                    conn.close()
                return resp
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
        raise ConnectionError("dot failed")

    def _plain(self, pkt):
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            u.settimeout(3)
            u.connect((self.cfg.upstream, self.cfg.upstream_port))     # only accept replies from the upstream itself
            u.send(pkt)
            for _ in range(4):
                data = u.recv(4096)
                if data[:2] == pkt[:2]:
                    return data
            raise ConnectionError("no matching reply")
        finally:
            u.close()

    def __call__(self, pkt):
        if not self.cfg.no_tls and (self.cfg.strict or self.clock() >= self._dot_down_until):
            try:
                r = self._dot(pkt)
                self.counters["tls"] += 1
                return r
            except Exception:
                if self.cfg.strict:
                    raise
                self._dot_down_until = self.clock() + DOT_RETRY_S
        r = self._plain(pkt)
        self.counters["plain"] += 1
        return r
