"""Dashboard access token: a file in the data dir (mode 600). Open the dashboard once with ?key=<token>; a cookie is used after that."""
import hmac
import os
import secrets

COOKIE = "ag"


def load_token(data_dir):
    path = os.path.join(data_dir, "token")
    try:
        with open(path) as f:
            t = f.read().strip()
        if len(t) >= 20:
            os.chmod(path, 0o600)
            return t
    except OSError:
        pass
    os.makedirs(data_dir, exist_ok=True)
    t = secrets.token_urlsafe(24)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(t)
    os.chmod(path, 0o600)
    return t


def same(a, b):
    return bool(a) and bool(b) and hmac.compare_digest(a.encode(), b.encode())


def cookie_value(header, name=COOKIE):
    for part in (header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return ""
