"""Dashboard access token. Anyone on the building network can reach the board, so the dashboard needs a key.
The key lives in the data dir (mode 600); the launcher fetches it and opens the dashboard with it once, after which
a cookie is used.

A second secret, <data_dir>/unlock, opens the stealth lock: with the token alone the dashboard shows no looked-up names.
Unlocking trades that secret for a short server-side session (cookie `ovu`)."""
import hmac
import os
import secrets
import threading
import time

COOKIE = "ov"
UNLOCK_COOKIE = "ovu"
SESSION_TTL = 30 * 60
MAX_SESSIONS = 16
MAX_FAILS, FAIL_WINDOW, MAX_TRACKED = 5, 60, 512
SECRET_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"     # no look-alikes: it is read off a file and typed on small keyboards


def _load(data_dir, name, minlen, make):
    path = os.path.join(data_dir, name)
    try:
        with open(path) as f:
            t = f.read().strip()
        if len(t) >= minlen:
            if os.stat(path).st_mode & 0o077:
                os.chmod(path, 0o600)           # a file made by hand or an older version must not stay readable by others
            return t
    except OSError:
        pass
    os.makedirs(data_dir, exist_ok=True)
    t = make()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(t)
    os.chmod(path, 0o600)                       # O_CREAT's mode is ignored when the file already exists
    return t


def load_token(data_dir):
    return _load(data_dir, "token", 20, lambda: secrets.token_urlsafe(24))


def load_secret(data_dir):
    return _load(data_dir, "unlock", 8, lambda: "".join(secrets.choice(SECRET_ALPHABET) for _ in range(12)))


def same(a, b):
    return bool(a) and bool(b) and hmac.compare_digest(a.encode(), b.encode())


def cookie_value(header, name=COOKIE):
    for part in (header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return ""


class Sessions:
    """Unlock sessions: random ids, fixed server-side expiry, at most `limit` alive (the oldest is dropped first)."""

    def __init__(self, ttl=SESSION_TTL, limit=MAX_SESSIONS, clock=time.monotonic):
        self.ttl, self.limit, self.clock = ttl, limit, clock
        self._s, self._lock = {}, threading.Lock()

    def start(self):
        sid = secrets.token_urlsafe(24)
        with self._lock:
            now = self.clock()
            self._s = {k: v for k, v in self._s.items() if v > now}
            while len(self._s) >= self.limit:
                del self._s[min(self._s, key=self._s.get)]
            self._s[sid] = now + self.ttl
        return sid

    def valid(self, sid):
        with self._lock:
            return bool(sid) and self._s.get(sid, 0) > self.clock()

    def end(self, sid):
        with self._lock:
            self._s.pop(sid, None)


class FailureLimit:
    """At most `limit` failures per `window` seconds per key; the table itself is bounded."""

    def __init__(self, limit=MAX_FAILS, window=FAIL_WINDOW, clock=time.monotonic, tracked=MAX_TRACKED):
        self.limit, self.window, self.clock, self.tracked = limit, window, clock, tracked
        self._f, self._lock = {}, threading.Lock()

    def _recent(self, key, now):
        return [t for t in self._f.get(key, ()) if now - t < self.window]

    def blocked(self, key):
        with self._lock:
            return len(self._recent(key, self.clock())) >= self.limit

    def fail(self, key):
        with self._lock:
            now = self.clock()
            if key not in self._f and len(self._f) >= self.tracked:
                self._f = {k: r for k in self._f if (r := self._recent(k, now))}
                if len(self._f) >= self.tracked:
                    del self._f[min(self._f, key=lambda k: self._f[k][-1])]
            self._f[key] = self._recent(key, now) + [now]
