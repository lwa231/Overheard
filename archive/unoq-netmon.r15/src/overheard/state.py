"""All live data in one place. Nothing else keeps module level mutable state."""
import collections
import threading
import time

from .services import classify

STEP, NBINS = 5, 120  # 5 s bins, 10 minutes of history
REFUSED_MAX = 64       # refused source addresses remembered


class State:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.started = clock()
        self.lock = threading.Lock()
        self.events = collections.deque(maxlen=20000)   # (t, client, domain, service, kind, blocked)
        self.hist = collections.deque(maxlen=600)       # (t, rx_bps, tx_bps)
        self.now = {"rx": 0.0, "tx": 0.0}
        self.total = {"rx": 0, "tx": 0}
        self.conns = []
        self.dns = {"enabled": False, "total": 0, "blocked": 0, "clients": {}, "tls": 0, "plain": 0}
        self.ipmap = {}
        self.rdns = {}
        self._seen = {}
        self.listeners = []   # callables (t, client, service, kind, blocked)
        self.refused = {}     # source address -> [count, last seen]; devices that asked but are outside the allowed networks

    def record(self, client, domain, blocked, adult=False):
        """Register one lookup. A + AAAA + HTTPS for the same name within a second count once."""
        t = self.clock()
        key = (client, domain)
        svc, kind = ("Adult content", "adult") if adult else ("Ads and trackers", "ads") if blocked else classify(domain)
        with self.lock:
            if t - self._seen.get(key, 0) < 1.0:
                return False
            self._seen[key] = t
            if len(self._seen) > 5000:
                self._seen.clear()
            self.events.append((t, client, domain, svc, kind, blocked or adult))
            self.dns["total"] += 1
            self.dns["blocked"] += int(blocked or adult)
            self.dns["clients"][client] = t
        for fn in self.listeners:
            fn(t, client, svc, kind, blocked or adult)
        return True

    def note_refused(self, ip):
        """Count a query we stayed silent on because its source is outside the allowed networks (shown on the dashboard)."""
        t = self.clock()
        with self.lock:
            row = self.refused.get(ip)
            if row:
                row[0] += 1
                row[1] = t
                return
            if len(self.refused) >= REFUSED_MAX:      # bounded: forget the one seen longest ago
                del self.refused[min(self.refused, key=lambda k: self.refused[k][1])]
            self.refused[ip] = [1, t]

    def remember_ips(self, ips, name):
        """Remember which hostname an address was resolved for (names this board's own flows)."""
        with self.lock:
            if len(self.ipmap) > 30000:
                self.ipmap.clear()
            for ip in ips:
                self.ipmap[ip] = name

    def add_flow(self, host, svc, kind):
        with self.lock:
            self.events.append((self.clock(), "this board", host, svc, kind, False))

    def set_net(self, rx, tx, rx_total=None, tx_total=None, add=False):
        with self.lock:
            self.now.update(rx=rx, tx=tx)
            if rx_total is not None:
                self.total.update(rx=rx_total, tx=tx_total)
            if add:
                self.total["rx"] += rx
                self.total["tx"] += tx
            self.hist.append((self.clock(), rx, tx))
