"""Tiny per-device behaviour profiles.

Stores only counts: (device, day-of-week, hour, category) -> n. No domains, no timestamps
of single lookups, so the file stays small and says nothing about what was looked at.
  hourly: all-time 7x24 grid per device (bounded: devices x 168 x categories rows)
  daily : per-day totals, pruned to DAILY_KEEP days
The database is size capped; when it is full new counts are dropped, never old ones.
"""
import json
import os
import sqlite3
import threading
import time

CATEGORIES = ("video", "audio", "social", "search", "gaming", "ads", "browse", "other")
SOCIAL = {"TikTok", "Instagram", "Facebook and Meta", "Reddit", "X", "Snapchat", "Discord"}
DAILY_KEEP = 90

SCHEMA = """
CREATE TABLE IF NOT EXISTS hourly(dev TEXT, dow INT, hour INT, cat INT, n INT, PRIMARY KEY(dev,dow,hour,cat));
CREATE TABLE IF NOT EXISTS daily(dev TEXT, day TEXT, cat INT, n INT, PRIMARY KEY(dev,day,cat));
"""


def categorize(service, kind, blocked):
    """Map a classified lookup to a profile category, or None if it carries no signal."""
    if service == "Adult content":
        return None          # deliberately never profiled
    if blocked:
        return "ads"
    if service == "System":
        return None
    if kind == "video":
        return "video"
    if kind == "audio":
        return "audio"
    if kind == "search":
        return "search"
    if service in SOCIAL:
        return "social"
    if service == "Steam":
        return "gaming"
    if service == "Other":
        return "other"
    return "browse"


class ProfileStore:
    def __init__(self, path, max_bytes=16 << 20, flush_s=120, devices=(), everyone=False, clock=time.time):
        self.path, self.flush_s, self.clock = path, flush_s, clock
        self.devices, self.everyone = set(devices), everyone
        self.lock = threading.Lock()      # guards pending
        self.dblock = threading.RLock()   # serialises every sqlite call
        self.pending = {}          # (dev, dow, hour, cat) -> n
        self.dropped = 0
        self._stop = threading.Event()
        self._thread = None
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        page = self.db.execute("PRAGMA page_size").fetchone()[0]
        self.db.execute("PRAGMA max_page_count=%d" % max(16, max_bytes // page))
        self.db.commit()

    # ----- collecting -----
    def wants(self, dev):
        return self.everyone or dev in self.devices

    def observe(self, t, dev, service, kind, blocked):
        """State listener: count one lookup in memory."""
        if not self.wants(dev):
            return
        cat = categorize(service, kind, blocked)
        if cat is None:
            return
        tm = time.gmtime(t)
        key = (dev, tm.tm_wday, tm.tm_hour, CATEGORIES.index(cat))
        with self.lock:
            self.pending[key] = self.pending.get(key, 0) + 1

    def flush(self):
        with self.lock:
            batch, self.pending = self.pending, {}
        if not batch:
            return
        day = time.strftime("%Y-%m-%d", time.gmtime(self.clock()))
        try:
            with self.dblock, self.db:
                for (dev, dow, hour, cat), n in batch.items():
                    self.db.execute("INSERT INTO hourly VALUES(?,?,?,?,?) ON CONFLICT(dev,dow,hour,cat) DO UPDATE SET n=n+excluded.n", (dev, dow, hour, cat, n))
                    self.db.execute("INSERT INTO daily VALUES(?,?,?,?) ON CONFLICT(dev,day,cat) DO UPDATE SET n=n+excluded.n", (dev, day, cat, n))
                cutoff = time.strftime("%Y-%m-%d", time.gmtime(self.clock() - DAILY_KEEP * 86400))
                self.db.execute("DELETE FROM daily WHERE day < ?", (cutoff,))
        except sqlite3.OperationalError:     # database full: drop this batch, keep what we have
            self.dropped += sum(batch.values())

    def start(self):
        def loop():
            while not self._stop.wait(self.flush_s):
                self.flush()
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self.flush()
        with self.dblock:
            self.db.close()

    # ----- reading -----
    def devices_seen(self):
        self.flush()
        with self.dblock:
            rows = self.db.execute("SELECT dev, SUM(n) FROM hourly GROUP BY dev ORDER BY dev").fetchall()
            days = dict(self.db.execute("SELECT dev, COUNT(DISTINCT day) FROM daily GROUP BY dev").fetchall())
        return [{"id": d, "lookups": int(n), "days": days.get(d, 0)} for d, n in rows]

    def profile(self, dev):
        self.flush()
        week = [[0] * len(CATEGORIES) for _ in range(168)]
        with self.dblock:
            rows = self.db.execute("SELECT dow,hour,cat,n FROM hourly WHERE dev=?", (dev,)).fetchall()
            days = self.db.execute("SELECT COUNT(DISTINCT day) FROM daily WHERE dev=?", (dev,)).fetchone()[0]
        for dow, hour, cat, n in rows:
            week[dow * 24 + hour][cat] = n
        total = sum(sum(r) for r in week)
        vec = [round(x / total, 6) for r in week for x in r] if total else []
        return {"id": dev, "cats": list(CATEGORIES), "week": week, "vector": vec, "total": total, "days_observed": days}

    def export_vectors(self):
        return {"cats": list(CATEGORIES), "layout": "dow(Mon=0,UTC) x hour x category, L1 normalised",
                "devices": {d["id"]: self.profile(d["id"])["vector"] for d in self.devices_seen()}}

    def purge(self):
        with self.lock:
            self.pending = {}
        with self.dblock:
            with self.db:
                self.db.execute("DELETE FROM hourly")
                self.db.execute("DELETE FROM daily")
            self.db.execute("VACUUM")

    def size_bytes(self):
        return os.path.getsize(self.path) if os.path.exists(self.path) else 0


def dumps_export(store):
    return json.dumps(store.export_vectors())
