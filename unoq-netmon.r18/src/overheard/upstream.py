"""Forward lookups upstream: DNS over TLS (a second provider if the first fails), plain UDP as the last fallback."""
import queue
import socket
import time
import ssl
import struct

DOT_RETRY_S = 60.0
CONNECT_S = 1.5       # a blocked port 853 must not hold a lookup: give up fast, answer over plain UDP


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
        c = cfg
        self.targets = [(c.upstream, c.tls_port, c.tls_name)] + ([(c.upstream2, c.tls_port2, c.tls_name2)] if c.upstream2 else [])
        self.pools = [queue.LifoQueue(maxsize=4) for _ in self.targets]
        self.pool = self.pools[0]
        self._down = [0.0] * len(self.targets)     # per provider circuit breaker (monotonic time until which it is skipped)
        self._ctx = None
        self._dot_down_until = 0.0     # after a TLS failure, go straight to plain UDP for a while so lookups do not each wait for the timeout
        self.clock = time.monotonic

    def _connect(self, i=0):
        c = self.cfg
        host, port, name = self.targets[i]
        if self._ctx is None:
            self._ctx = ssl.create_default_context(cafile=c.tls_cafile) if c.tls_cafile else ssl.create_default_context()
        s = socket.create_connection((host, port), timeout=CONNECT_S)
        return self._ctx.wrap_socket(s, server_hostname=name)

    def _dot(self, pkt):
        err = ConnectionError("dot failed")
        for i in range(len(self.targets)):
            if self.clock() < self._down[i] and not self.cfg.strict:
                continue
            try:
                return self._dot_one(pkt, i)
            except TimeoutError:           # port 853 is filtered (or the server hangs): a second provider would only add another wait
                self._down = [self.clock() + DOT_RETRY_S] * len(self.targets)
                raise
            except Exception as e:
                self._down[i] = self.clock() + DOT_RETRY_S
                err = e
        raise err

    def _dot_one(self, pkt, i):
        for pooled in (True, False):
            try:
                conn = self.pools[i].get_nowait() if pooled else self._connect(i)
            except queue.Empty:
                continue                       # nothing pooled: go straight to a fresh connection
            try:
                conn.settimeout(3)
                conn.sendall(struct.pack("!H", len(pkt)) + pkt)
                resp = _recvn(conn, struct.unpack("!H", _recvn(conn, 2))[0])
                if resp[:2] != pkt[:2]:
                    raise ConnectionError("id mismatch")
                try:
                    self.pools[i].put_nowait(conn)
                except queue.Full:
                    conn.close()
                return resp
            except Exception as e:
                try:
                    conn.close()
                except Exception:
                    pass
                if isinstance(e, TimeoutError) and not pooled:
                    raise                      # accepted but never answered: the caller treats it like a filtered port, no wait on a second provider
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
