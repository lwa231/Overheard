"""Dashboard access token. Anyone on the building network can reach the board, so the dashboard needs a key.
The key lives in the data dir (mode 600); the launcher fetches it and opens the dashboard with it once, after which
a cookie is used."""
import hmac
import os
import secrets

COOKIE = "ov"


def load_token(data_dir):
    path = os.path.join(data_dir, "token")
    try:
        with open(path) as f:
            t = f.read().strip()
        if len(t) >= 20:
            return t
    except OSError:
        pass
    os.makedirs(data_dir, exist_ok=True)
    t = secrets.token_urlsafe(24)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(t)
    return t


def same(a, b):
    return bool(a) and bool(b) and hmac.compare_digest(a.encode(), b.encode())


def cookie_value(header):
    for part in (header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == COOKIE:
            return v
    return ""
