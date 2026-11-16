"""Background collectors: this board's own traffic and its open connections."""
import collections
import random
import re
import socket
import subprocess
import threading
import time

from .services import classify

PRIVATE = ("10.", "192.168.", "127.", "169.254.", "::1", "fe80", "100.64.", "100.65.", "100.66.", "100.67.", "100.68.", "100.69.")


def is_private(ip):
    if ip.startswith(PRIVATE):
        return True
    return ip.startswith("172.") and 16 <= int(ip.split(".")[1] or 0) <= 31


def read_net(path="/proc/net/dev"):
    rx = tx = 0
    with open(path) as f:
        lines = list(f)[2:]
    for line in lines:
        name, data = line.split(":", 1)
        if name.strip() == "lo":
            continue
        v = data.split()
        rx += int(v[0])
        tx += int(v[8])
    return rx, tx


def net_sampler(state, demo=False, interval=1.0):
    if demo:
        while True:
            state.set_net(random.expovariate(1 / 90000), random.expovariate(1 / 20000), add=True)
            time.sleep(interval)
    prev, pt = read_net(), time.time()
    while True:
        time.sleep(interval)
        cur, ct = read_net(), time.time()
        dt = max(ct - pt, .001)
        state.set_net((cur[0] - prev[0]) / dt, (cur[1] - prev[1]) / dt, cur[0], cur[1])
        prev, pt = cur, ct


def _reverse(state, ip):
    if ip not in state.rdns:
        state.rdns[ip] = ""

        def look():
            try:
                state.rdns[ip] = socket.gethostbyaddr(ip)[0]
            except Exception:
                pass
        threading.Thread(target=look, daemon=True).start()
    return state.rdns[ip]


def parse_ss(text):
    """Return (connection counts, bytes received) per remote public IP from `ss -tni` output."""
    agg, cnt, last = collections.Counter(), collections.Counter(), None
    for ln in text.splitlines():
        if ln and ln[0] not in " \t":
            p = ln.split()
            last = p[-1].rsplit(":", 1)[0].strip("[]") if len(p) >= 4 else None
            if last and not is_private(last):
                cnt[last] += 1
            else:
                last = None
        elif last:
            m = re.search(r"bytes_received:(\d+)", ln)
            if m:
                agg[last] += int(m.group(1))
    return cnt, agg


def conn_poller(state, interval=4.0):
    """Flows opened by the board itself, named through the DNS answers it has seen."""
    while True:
        try:
            out = subprocess.run(["ss", "-tniH", "state", "established"], capture_output=True, text=True, timeout=5).stdout
            cnt, agg = parse_ss(out)
        except Exception:
            cnt, agg = collections.Counter(), collections.Counter()
        res = []
        for ip, n in cnt.most_common(12):
            host = state.ipmap.get(ip) or _reverse(state, ip) or ip
            svc, kind = classify(host)
            res.append({"ip": ip, "host": host, "service": svc, "count": n, "bytes": agg[ip]})
            if svc not in ("Other", "System"):
                state.add_flow(host, svc, "flow" if kind in ("static", "feed", "other") else kind)
        with state.lock:
            state.conns = res
        time.sleep(interval)
