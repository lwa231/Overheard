"""The board's own vitals (CPU, memory, temperature, disk, load) read from /proc and /sys. Standard library only."""
import collections
import glob
import os
import random
import shutil
import socket
import subprocess
import time

HISTORY = 60
NET_EVERY = 15          # vitals samples between looks at the network (about 30 s)


def read_cpu_times(path="/proc/stat"):
    """(busy, total) jiffies summed over all cores."""
    with open(path) as f:
        v = [int(x) for x in f.readline().split()[1:]]
    idle = v[3] + (v[4] if len(v) > 4 else 0)
    return sum(v) - idle, sum(v)


def cpu_percent(prev, cur):
    db, dt = cur[0] - prev[0], cur[1] - prev[1]
    return max(0.0, min(100.0, 100.0 * db / dt)) if dt > 0 else 0.0


def read_memory(path="/proc/meminfo"):
    """(used_bytes, total_bytes); 'used' excludes reclaimable cache so it matches what a task manager shows."""
    m = {}
    with open(path) as f:
        for line in f:
            k, _, rest = line.partition(":")
            if k in ("MemTotal", "MemAvailable"):
                m[k] = int(rest.split()[0]) * 1024
    total = m.get("MemTotal", 0)
    return max(0, total - m.get("MemAvailable", total)), total


def read_temperature(pattern="/sys/class/thermal/thermal_zone*/temp"):
    """Hottest thermal zone in degrees C, or None when the board exposes none."""
    best = None
    for p in glob.glob(pattern):
        try:
            with open(p) as f:
                c = int(f.read().strip()) / 1000.0
        except (OSError, ValueError):
            continue
        if -40 < c < 150 and (best is None or c > best):
            best = c
    return best


def read_uptime(path="/proc/uptime"):
    with open(path) as f:
        return float(f.read().split()[0])


class Vitals:
    """Holds the latest readings plus a short CPU history. Written by `sample`, read by the stats builder."""

    def __init__(self):
        self.cpu_hist = collections.deque(maxlen=HISTORY)
        self.latest = {}
        self.net = {}      # the network this board is on: {"iface", "gateway", "addr", "wireless", "ssid"}

    def snapshot(self):
        return dict(self.latest, cpu_hist=list(self.cpu_hist))


def read_default_route(path="/proc/net/route"):
    """(interface, gateway address) of the default route with the lowest metric, or None."""
    best = None
    try:
        with open(path) as f:
            for line in f.readlines()[1:]:
                p = line.split()
                if len(p) < 7 or p[1] != "00000000" or not int(p[3], 16) & 2:
                    continue
                gw = socket.inet_ntoa(bytes.fromhex(p[2])[::-1])        # the kernel prints it little-endian
                if best is None or int(p[6]) < best[0]:
                    best = (int(p[6]), p[0], gw)
    except (OSError, ValueError):
        return None
    return best[1:] if best else None


def _clean(text, limit=32):
    """A network name is chosen by whoever runs the network: keep printable characters only, and not many."""
    return "".join(c for c in text if c.isprintable())[:limit].strip()


def read_ssid(iface, run=None):
    """Name of the Wi-Fi network on iface, or "" if it cannot be read. Never raises."""
    run = run or (lambda argv: subprocess.run(argv, capture_output=True, text=True, timeout=3).stdout)
    for tool, args, pick in (
            ("iwgetid", [iface, "-r"], lambda out: out.strip()),
            ("nmcli", ["-t", "-f", "active,ssid", "dev", "wifi"],
             lambda out: next((ln[4:] for ln in out.splitlines() if ln.startswith("yes:")), ""))):
        exe = shutil.which(tool)
        if not exe:
            continue
        try:
            name = _clean(pick(run([exe] + args)))
        except (OSError, subprocess.SubprocessError, ValueError):
            continue
        if name:
            return name
    return ""


def read_network(route_path="/proc/net/route", sys_net="/sys/class/net", run=None):
    """Where this board plugs into the world: interface, gateway, its own address there, and the Wi-Fi name if any."""
    route = read_default_route(route_path)
    if not route:
        return {}
    iface, gw = route
    addr = ""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((gw, 9))                 # no packet is sent; this only asks the kernel which address it would use
            addr = s.getsockname()[0]
    except OSError:
        pass
    wireless = os.path.isdir(os.path.join(sys_net, iface, "wireless"))
    return {"iface": _clean(iface, 16), "gateway": gw, "addr": addr, "wireless": wireless,
            "ssid": read_ssid(iface, run) if wireless else ""}


def sample(vitals, prev, disk_path="/"):
    cur = read_cpu_times()
    pct = cpu_percent(prev, cur)
    used, total = read_memory()
    du = shutil.disk_usage(disk_path)
    try:
        load = os.getloadavg()[0]
    except OSError:
        load = 0.0
    vitals.cpu_hist.append(round(pct, 1))
    vitals.latest = {"cpu": round(pct, 1), "cores": os.cpu_count() or 1, "mem_used": used, "mem_total": total,
                     "temp": read_temperature(), "disk_used": du.used, "disk_total": du.total, "load": round(load, 2), "uptime": read_uptime()}
    return cur


def sampler(vitals, demo=False, interval=2.0):
    if demo:
        cpu, t0 = 18.0, time.time()
        vitals.net = {"iface": "wlan0", "gateway": "192.168.1.1", "addr": "192.168.1.2", "wireless": True, "ssid": "Home Wi-Fi"}
        while True:
            cpu = max(3.0, min(95.0, cpu + random.uniform(-7, 7)))
            vitals.cpu_hist.append(round(cpu, 1))
            vitals.latest = {"cpu": round(cpu, 1), "cores": 4, "mem_used": int(1.1e9 + random.uniform(-4e7, 4e7)), "mem_total": 2 * 1024 ** 3,
                             "temp": round(46 + cpu / 6, 1), "disk_used": int(7.4e9), "disk_total": int(29.4e9), "load": round(cpu / 40, 2), "uptime": time.time() - t0 + 86400}
            time.sleep(interval)
    prev, n = read_cpu_times(), 0
    while True:
        if n % NET_EVERY == 0:
            try:
                vitals.net = read_network()
            except Exception:               # a display nicety must never stop the vitals
                pass
        n += 1
        time.sleep(interval)
        try:
            prev = sample(vitals, prev)
        except (OSError, ValueError):
            pass
