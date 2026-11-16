"""Adult-content guard.

DNS can do two things here, and only two:
  1. refuse to resolve a known adult site (the site itself never loads), and
  2. make every other lookup from the offending device slow, for a cooldown after its last adult lookup.
It cannot throttle a connection that is already open, and a browser using its own DNS-over-HTTPS bypasses it.
Only devices that use this board as their DNS server are affected, and only the device that asked.
"""
import json
import os
import threading
import time
import urllib.request

SOURCES = (   # each checked to download and parse; unavailable ones are skipped with a log line
    "https://raw.githubusercontent.com/StevenBlack/hosts/master/alternates/porn-only/hosts",
    "https://raw.githubusercontent.com/4skinSkywalker/Anti-Porn-HOSTS-File/master/HOSTS.txt",
    "https://raw.githubusercontent.com/Sinfonietta/hostfiles/master/pornography-hosts",
)
MAX_BYTES = 40 << 20
TLDS = frozenset({"xxx", "porn", "sex", "adult"})
LABELS = frozenset({"sex", "xxx"})
# substrings that are almost never innocent inside a hostname label
FRAGMENTS = ("porn", "hentai", "xvideo", "xnxx", "xhamster", "redtube", "youporn", "onlyfans", "camgirl", "chaturbate", "stripchat", "livejasmin", "bangbros", "brazzers")
# Shared infrastructure that the downloaded lists sometimes mention (telemetry, ad and CDN hosts). Flagging these slows a whole device
# for something it does in the background, so they are never treated as adult. Fixed in code, like the rest of the guard.
NEVER_FLAG = ("apple.com", "icloud.com", "microsoft.com", "windows.com", "live.com", "office.com", "yahoo.com", "bing.net", "bing.com",
              "google.com", "googleapis.com", "gstatic.com", "amazonaws.com", "cloudfront.net", "cdn.cloudflare.net", "github.io", "akamaihd.net",
              "youtube.com", "googlevideo.com", "ytimg.com", "ggpht.com", "youtu.be")
MAX_FLAGS = 5000


def _norm(name):
    return name.lower().rstrip(".")


def parse_list(text):
    """Accepts hosts-file lines ('0.0.0.0 domain') and plain one-domain-per-line lists."""
    out = set()
    for ln in text.splitlines():
        ln = ln.split("#", 1)[0].strip()
        if not ln:
            continue
        parts = ln.split()
        d = parts[-1] if len(parts) > 1 and parts[0] in ("0.0.0.0", "127.0.0.1") else (parts[0] if len(parts) == 1 else None)
        if d and "." in d and d not in ("0.0.0.0", "127.0.0.1", "localhost") and all(c.isalnum() or c in "-._" for c in d):
            out.add(d.lower())
    return out


MIN_LIST = 1000      # a list smaller than this is treated as missing


class AdultFilter:
    def __init__(self, domains=()):
        self.domains = set(domains)

    def __len__(self):
        return len(self.domains)

    @staticmethod
    def _parents(name):
        p = name.split(".")
        return (".".join(p[k:]) for k in range(len(p) - 1))

    def check(self, name):
        """None, 'list' (known adult site) or 'heuristic' (hostname looks adult)."""
        d = _norm(name)
        if any(d == s or d.endswith("." + s) for s in NEVER_FLAG):
            return None
        if any(x in self.domains for x in self._parents(d)):
            return "list"
        labels = d.split(".")
        if labels[-1] in TLDS:
            return "heuristic"
        for lab in labels[:-1]:
            if lab in LABELS or any(f in lab for f in FRAGMENTS):
                return "heuristic"
        return None

    @classmethod
    def load(cls, data_dir, update=False, log=print):
        path = os.path.join(data_dir, "adult.txt")
        domains = set()
        if os.path.exists(path):
            with open(path) as f:
                domains = {x.strip() for x in f if x.strip()}
        if update or len(domains) < MIN_LIST:               # missing, empty or truncated: fetch again
            got = set()
            for url in SOURCES:
                try:
                    got |= parse_list(urllib.request.urlopen(url, timeout=25).read(MAX_BYTES).decode(errors="ignore"))
                except Exception as e:
                    log("adult list unavailable (%s): %s" % (url.split("/")[4], e))
            if len(got) >= MIN_LIST and len(got) * 2 >= len(domains):     # never replace a good list with a much smaller one
                os.makedirs(data_dir, exist_ok=True)
                tmp = path + ".tmp"
                with open(tmp, "w") as f:
                    f.write("\n".join(sorted(got)))
                os.replace(tmp, path)
                domains = got
        if len(domains) < MIN_LIST:
            log("adult list missing or incomplete: only the built-in name rules are fully active until it downloads")
        return cls(domains)


class PenaltyBox:
    """Devices that recently looked up adult content. Each is slowed until `cooldown` seconds after its last one."""

    def __init__(self, cooldown=90, clock=time.monotonic):
        self.cooldown, self.clock = cooldown, clock
        self.until = {}
        self.lock = threading.Lock()

    def trip(self, client):
        with self.lock:
            now = self.clock()
            if len(self.until) >= 2000:                   # drop finished entries so spoofed addresses cannot grow this forever
                self.until = {c: u for c, u in self.until.items() if u > now}
                if len(self.until) >= 2000:
                    self.until.pop(next(iter(self.until)))
            self.until[client] = now + self.cooldown

    def remaining(self, client):
        with self.lock:
            left = self.until.get(client, 0) - self.clock()
            if left <= 0:
                self.until.pop(client, None)
                return 0.0
            return left

    def active(self):
        now = self.clock()
        with self.lock:
            return [{"id": c, "left": round(u - now)} for c, u in sorted(self.until.items()) if u > now]


class FlagLog:
    """Domains that were flagged, with counts. No device identifiers are stored."""

    def __init__(self, path, clock=time.time):
        self.path, self.clock, self.lock = path, clock, threading.Lock()
        self.items = {}
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.items = {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, dict) and isinstance(v.get("hits"), int)
                              and isinstance(v.get("first"), (int, float)) and isinstance(v.get("last"), (int, float)) and isinstance(v.get("reason"), str)}
        except (OSError, ValueError):
            pass

    def add(self, domain, reason):
        d = _norm(domain)
        now = int(self.clock())
        with self.lock:
            it = self.items.get(d)
            if it:
                it["hits"] += 1
                it["last"] = now
            else:
                if len(self.items) >= MAX_FLAGS:
                    del self.items[min(self.items, key=lambda k: self.items[k]["last"])]
                self.items[d] = {"hits": 1, "reason": reason, "first": now, "last": now}

    def snapshot(self):
        with self.lock:
            return [{"domain": d, **v} for d, v in sorted(self.items.items(), key=lambda kv: -kv[1]["last"])]

    def save(self):
        with self.lock:
            data = json.dumps(self.items)
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            f.write(data)
        os.replace(tmp, self.path)


class Guard:
    """The three parts together, handed to the DNS server and the API."""

    def __init__(self, filt, penalty, flags):
        self.filter, self.penalty, self.flags = filt, penalty, flags

    def hit(self, client, name):
        """Check a lookup. On a hit: log it and put the device in the penalty box. Returns the reason or None."""
        reason = self.filter.check(name)
        if reason:
            self.penalty.trip(client)         # first: the slowdown must never depend on the log working
            try:
                self.flags.add(name, reason)
            except Exception:
                pass
        return reason

    def summary(self):
        return {"enabled": True, "slowed": self.penalty.active(), "flagged": len(self.flags.items), "listed": len(self.filter)}
