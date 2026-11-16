"""The ONLY outbound network calls in this program (a test checks that no other module opens a connection):
1. `ask_model`: POST to a local Ollama server, loopback only.
2. `fetch_price`: GET one public spot price from a host on the config allow-list (`test_mode.price_hosts`); any other host is refused before a request is made.
Redirects are never followed. A reply is only ever read as text/JSON: never executed, never used as a URL, path or command. Agents get no tool that calls any of this."""
import json
import math
import queue
import re
import threading
import time
import urllib.error
import urllib.request
import weakref
from urllib.parse import urlparse

LOOPBACK = ("127.0.0.1", "localhost", "::1")
MAX_REPLY = 1 << 20             # bytes read from any server
MAX_TEXT = 8000                 # characters kept of a model reply
SPOT_URL = "https://api.coinbase.com/v2/prices/%s/spot"        # Coinbase public spot price (crypto only; verified live, see README)
SYMBOL_RE = re.compile(r"^[A-Z]{2,10}-USD$")


class NetError(OSError):
    """A request was refused, failed, timed out or got an unusable answer."""


class ModelError(NetError):
    pass


class PriceError(NetError):
    pass


def _loop(q, done):
    while True:
        job = q.get()
        if job is None:
            return
        tag, fn, args = job
        t = time.monotonic()
        try:
            out = fn(*args)
        except Exception as e:  # noqa: BLE001 - whatever a call raises is handed back as its result
            out = e
        done.append((tag, out, time.monotonic() - t))
        q.task_done()


class Worker:
    """The one background thread that makes the slow calls (model, price fetch), one at a time. A caller `submit`s and later `collect`s; it never waits."""
    def __init__(self):
        self.q, self.done = queue.Queue(), []
        threading.Thread(target=_loop, args=(self.q, self.done), daemon=True).start()
        weakref.finalize(self, self.q.put, None)

    def submit(self, tag, fn, *args):
        self.q.put((tag, fn, args))

    def collect(self):
        """-> [(tag, result or the exception it raised, seconds)] finished since the last call."""
        got = []
        while self.done:
            got.append(self.done.pop(0))
        return got

    def join(self):
        """Wait until everything submitted has finished (tests only; the server never waits)."""
        self.q.join()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _opener(direct):
    """direct: no proxy from the environment (the model is on this machine)."""
    h = [_NoRedirect()] + ([urllib.request.ProxyHandler({})] if direct else [])
    return urllib.request.build_opener(*h)


def _read(req, direct, timeout, deadline):
    """The request itself, on its own thread: chunked, so a server that drips bytes cannot go on past `deadline`."""
    with _opener(direct).open(req, timeout=timeout) as r:
        body = b""
        while len(body) <= MAX_REPLY:
            if time.monotonic() > deadline:
                raise NetError("deadline passed")
            chunk = r.read1(65536)
            if not chunk:
                break
            body += chunk
    return body


def _get(url, hosts, timeout, data=None):
    """One request to a host on `hosts` (lower case names); returns the body bytes. Refuses anything else before connecting.
    `timeout` is a TOTAL deadline in seconds for connect, send and the whole reply (not just one read)."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or (u.hostname or "").lower() not in hosts:
        raise NetError("host %r is not on the allow-list" % (u.hostname,))
    req = urllib.request.Request(url, data, {"Content-Type": "application/json"} if data else {}, method="POST" if data else "GET")
    out = []

    def go():
        try:
            out.append(_read(req, hosts is LOOPBACK, timeout, time.monotonic() + timeout))
        except Exception as e:  # noqa: BLE001 - handed to the caller below
            out.append(e)
    t = threading.Thread(target=go, daemon=True)
    t.start()
    t.join(timeout)
    if not out:                                                          # still running at the deadline: give up on it (the thread ends at its next chunk or read timeout)
        raise NetError("request failed: deadline of %gs passed" % timeout)
    if isinstance(out[0], NetError):
        raise out[0]
    if isinstance(out[0], (urllib.error.URLError, OSError, ValueError)):          # HTTPError, timeouts, refused connections, bad URLs
        raise NetError("request failed: %s" % type(out[0]).__name__) from None
    if isinstance(out[0], Exception):
        raise out[0]
    if len(out[0]) > MAX_REPLY:
        raise NetError("reply too large")
    return out[0]


def ask_model(prompt, url, model, timeout, keep_alive="30m", num_ctx=4096, num_predict=512):
    """-> the model's reply as text (non-streaming Ollama /api/generate). url must be on this machine. keep_alive keeps the model loaded between calls; num_ctx and
    num_predict cap the context window and the reply length. Raises ModelError."""
    try:
        req = {"model": model, "prompt": prompt, "stream": False, "keep_alive": keep_alive, "options": {"num_ctx": num_ctx, "num_predict": num_predict}}
        body = _get(url, LOOPBACK, timeout, json.dumps(req).encode())
        text = json.loads(body)["response"]
    except (NetError, ValueError, KeyError, TypeError, RecursionError) as e:
        raise ModelError("model gave no usable answer (%s)" % type(e).__name__) from None
    if not isinstance(text, str) or not text.strip():
        raise ModelError("model reply was empty")
    return text[:MAX_TEXT]


def parse_spot(body, symbol):
    """Coinbase spot reply {"data": {"amount": "73654.275", "base": "BTC", "currency": "USD"}} -> price (float > 0, finite). Anything else raises PriceError."""
    try:
        d = json.loads(body)["data"]
        price = float(d["amount"])
        ok = isinstance(d["amount"], str) and d["base"] + "-" + d["currency"] == symbol and math.isfinite(price) and 0 < price < 1e9
    except (ValueError, KeyError, TypeError, RecursionError):
        ok = False
    if not ok:
        raise PriceError("malformed price data for %s" % symbol)
    return price


def fetch_price(symbol, hosts, timeout=10):
    """The spot price of a crypto pair like BTC-USD from Coinbase, only if its host is on `hosts`."""
    if not isinstance(symbol, str) or not SYMBOL_RE.match(symbol):
        raise PriceError("bad symbol")
    return parse_spot(_get(SPOT_URL % symbol, tuple(h.lower() for h in hosts), timeout), symbol)
