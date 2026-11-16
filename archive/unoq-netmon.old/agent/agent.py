#!/usr/bin/env python3
"""Overheard: headless DNS listener for the Arduino UNO Q.
Classifies the DNS lookups of devices that use this board as their DNS server
(YouTube, TikTok, Netflix ...), blocks ad/tracker domains, and serves a live dashboard.
  python3 agent.py --dns          (needs root for port 53)
  python3 agent.py --demo         (scripted fake traffic, UI preview)
DNS only shows WHICH service a device talks to, never what is played or searched."""
import argparse, collections, json, os, queue, random, socket, ssl, struct, subprocess, threading, time, re, urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
LOCK = threading.Lock()
START = time.time()
STEP, NBINS = 5, 120                      # 5 s bins, 10 minutes
EVENTS = collections.deque(maxlen=20000)  # (t, client, domain, service, kind, blocked)
HIST = collections.deque(maxlen=600)      # (t, rx_bps, tx_bps)
NOW = {"rx": 0, "tx": 0}
TOT = {"rx": 0, "tx": 0}
CONNS = []
DNS = {"enabled": False, "total": 0, "blocked": 0, "clients": {}, "tls": 0, "plain": 0}
POOL = queue.LifoQueue()
BLOCK, IPMAP, RDNS, SEEN = set(), {}, {}, {}
ARGS = None

# ---------- service table: suffix -> (service, kind).  "=" prefix = exact host ----------
SERVICES = {
 "YouTube": {"video": ["googlevideo.com"], "feed": ["youtube.com", "youtu.be", "youtubei.googleapis.com", "youtube-nocookie.com"], "static": ["ytimg.com", "ggpht.com"]},
 "TikTok": {"video": ["tiktokcdn.com", "tiktokcdn-us.com", "ibytedtos.com", "muscdn.com"], "feed": ["tiktok.com", "tiktokv.com", "tiktokv.us", "byteoversea.com", "tiktokw.us"], "static": ["ibyteimg.com", "ttwstatic.com"]},
 "Instagram": {"media": ["cdninstagram.com"], "feed": ["instagram.com"]},
 "Facebook and Meta": {"media": ["fbcdn.net", "fbsbx.com"], "feed": ["facebook.com", "fb.com", "messenger.com", "whatsapp.net", "whatsapp.com", "threads.net"]},
 "Netflix": {"video": ["nflxvideo.net"], "feed": ["netflix.com", "nflxext.com", "nflxso.net"], "static": ["nflximg.net"]},
 "Prime Video": {"video": ["aiv-cdn.net", "aiv-delivery.net", "pv-cdn.net"], "feed": ["primevideo.com", "amazonvideo.com"]},
 "Disney+": {"video": ["bamgrid.com", "dssott.com"], "feed": ["disneyplus.com", "disney-plus.net"]},
 "Hulu": {"video": ["hulustream.com"], "feed": ["hulu.com", "huluim.com"]},
 "Twitch": {"video": ["ttvnw.net", "live-video.net"], "feed": ["twitch.tv"], "static": ["jtvnw.net"]},
 "Spotify": {"audio": ["scdn.co", "spotifycdn.com", "audio-ak-spotify-com.akamaized.net"], "feed": ["spotify.com"]},
 "Reddit": {"media": ["redd.it", "redditmedia.com", "redditstatic.com"], "feed": ["reddit.com"]},
 "X": {"media": ["twimg.com"], "feed": ["twitter.com", "x.com", "t.co"]},
 "Discord": {"video": ["discord.media"], "feed": ["discord.com", "discordapp.com", "discord.gg", "discordapp.net"]},
 "Zoom": {"video": ["zoom.us", "zoom.com"]},
 "Snapchat": {"media": ["sc-cdn.net"], "feed": ["snapchat.com"]},
 "Steam": {"media": ["steamcontent.com", "steamstatic.com"], "feed": ["steampowered.com", "steamcommunity.com"]},
 "Google search": {"search": ["=www.google.com", "=google.com", "=www.bing.com", "=duckduckgo.com", "=search.brave.com", "=search.yahoo.com"]},
 "Google": {"feed": ["google.com", "gmail.com"], "static": ["gstatic.com", "googleapis.com", "googleusercontent.com", "gvt1.com"]},
 "System": {"system": ["apple.com", "icloud.com", "mzstatic.com", "microsoft.com", "windowsupdate.com", "msftconnecttest.com", "debian.org", "ubuntu.com", "arduino.cc", "cloudflare-dns.com", "ocsp.digicert.com"]},
}
RULES, EXACT = {}, {}
for svc, kinds in SERVICES.items():
    for kind, sfx in kinds.items():
        for s in sfx:
            (EXACT if s.startswith("=") else RULES)[s.lstrip("=")] = (svc, kind)
WEIGHT = {"video": 3, "audio": 2, "search": 2.5, "media": 1.5, "feed": 1, "static": 0.3, "flow": 1, "system": 0, "other": 0.2, "ads": 0}

def classify(domain):
    d = domain.lower().rstrip(".")
    if d in EXACT: return EXACT[d]
    p = d.split(".")
    for k in range(len(p) - 1):
        hit = RULES.get(".".join(p[k:]))
        if hit: return hit
    return ("Other", "other")

# ---------- DNS ----------
def load_blocklist(update=False):
    path = os.path.join(HERE, "blocklist.txt")
    if update or not os.path.exists(path):
        try:
            data = urllib.request.urlopen("https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts", timeout=25).read().decode()
            doms = {l.split()[1].lower() for l in data.splitlines() if l.startswith("0.0.0.0 ") and len(l.split()) > 1 and l.split()[1] != "0.0.0.0"}
            open(path, "w").write("\n".join(sorted(doms)))
        except Exception as e:
            print("blocklist download failed:", e)
    if os.path.exists(path):
        BLOCK.update(x.strip() for x in open(path) if x.strip())
    print("blocklist entries:", len(BLOCK))

def is_blocked(d):
    p = d.split(".")
    return any(".".join(p[k:]) in BLOCK for k in range(len(p) - 1))

def parse_q(pkt):
    i, labels = 12, []
    while pkt[i]:
        n = pkt[i]; labels.append(pkt[i+1:i+1+n].decode(errors="ignore")); i += n + 1
    return ".".join(labels).lower(), struct.unpack("!H", pkt[i+1:i+3])[0], i + 5

def skip_name(b, i):
    while True:
        l = b[i]
        if l == 0: return i + 1
        if l & 0xC0 == 0xC0: return i + 2
        i += l + 1

def process_reply(resp, maxttl):
    """Cap answer TTLs (so clients re-ask often = better signal) and return (resp, [A-record ips])."""
    ips = []
    try:
        b = bytearray(resp)
        qd, an = struct.unpack("!HH", b[4:8]); i = 12
        for _ in range(qd): i = skip_name(b, i) + 4
        for _ in range(an):
            i = skip_name(b, i)
            typ, _c, ttl, rdlen = struct.unpack("!HHIH", b[i:i+10])
            if maxttl and ttl > maxttl: b[i+4:i+8] = struct.pack("!I", maxttl)
            if typ == 1 and rdlen == 4: ips.append(socket.inet_ntoa(bytes(b[i+10:i+14])))
            i += 10 + rdlen
        return bytes(b), ips
    except Exception:
        return resp, ips

def record(client, domain, blocked):
    key = (client, domain); t = time.time()
    if t - SEEN.get(key, 0) < 1.0: return           # A + AAAA + HTTPS = one lookup
    SEEN[key] = t
    if len(SEEN) > 5000: SEEN.clear()
    svc, kind = ("Ads and trackers", "ads") if blocked else classify(domain)
    with LOCK:
        EVENTS.append((t, client, domain, svc, kind, blocked))
        DNS["total"] += 1; DNS["blocked"] += blocked
        DNS["clients"][client] = t

def _recvn(t, n):
    b = b""
    while len(b) < n:
        c = t.recv(n - len(b))
        if not c: raise ConnectionError("closed")
        b += c
    return b

def _dot_conn():
    ctx = ssl.create_default_context(cafile=ARGS.tls_cafile) if ARGS.tls_cafile else ssl.create_default_context()
    s = socket.create_connection((ARGS.upstream, ARGS.tls_port), timeout=3)
    return ctx.wrap_socket(s, server_hostname=ARGS.tls_name)

def dot_query(pkt):
    """DNS over TLS: the building/ISP sees a TLS connection, not the names being looked up."""
    for attempt in (0, 1):
        try: c = POOL.get_nowait() if attempt == 0 else _dot_conn()
        except queue.Empty: c = _dot_conn()
        try:
            c.settimeout(3); c.sendall(struct.pack("!H", len(pkt)) + pkt)
            resp = _recvn(c, struct.unpack("!H", _recvn(c, 2))[0])
            POOL.put(c); return resp
        except Exception:
            try: c.close()
            except Exception: pass
    raise ConnectionError("dot failed")

def forward(pkt):
    if not ARGS.no_tls:
        try:
            r = dot_query(pkt); DNS["tls"] += 1; return r
        except Exception:
            if ARGS.strict: raise
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); u.settimeout(3)
    u.sendto(pkt, (ARGS.upstream, 53)); data = u.recvfrom(4096)[0]; u.close(); DNS["plain"] += 1
    return data

def handle(sock, pkt, addr, upstream, maxttl):
    try: name, qtype, end = parse_q(pkt)
    except Exception: return
    blocked = is_blocked(name)
    record(addr[0], name, blocked)
    if blocked:
        resp = pkt[:2] + b"\x81\x80" + pkt[4:6] + (b"\x00\x01" if qtype == 1 else b"\x00\x00") + b"\x00\x00\x00\x00" + pkt[12:end]
        if qtype == 1: resp += b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04\x00\x00\x00\x00"
        sock.sendto(resp, addr); return
    try:
        data, ips = process_reply(forward(pkt), maxttl)
        if len(IPMAP) > 30000: IPMAP.clear()
        for ip in ips: IPMAP[ip] = name
        sock.sendto(data, addr)
    except Exception: pass

def dns_server(port, upstream, maxttl, bind="0.0.0.0"):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind((bind, port)); DNS["enabled"] = True
    print("DNS on :%d -> %s (ttl cap %ss)" % (port, upstream, maxttl or "off"))
    while True:
        pkt, addr = s.recvfrom(4096)
        threading.Thread(target=handle, args=(s, pkt, addr, upstream, maxttl), daemon=True).start()

# ---------- this board's own line ----------
def read_net():
    rx = tx = 0
    for line in list(open("/proc/net/dev"))[2:]:
        name, data = line.split(":", 1)
        if name.strip() == "lo": continue
        v = data.split(); rx += int(v[0]); tx += int(v[8])
    return rx, tx

def sampler():
    if ARGS.demo:
        while True:
            rx, tx = random.expovariate(1/90000), random.expovariate(1/20000)
            with LOCK: NOW.update(rx=rx, tx=tx); TOT["rx"] += rx; TOT["tx"] += tx; HIST.append((time.time(), rx, tx))
            time.sleep(1)
    prev, pt = read_net(), time.time()
    while True:
        time.sleep(1); cur, ct = read_net(), time.time(); dt = max(ct - pt, .001)
        with LOCK:
            NOW.update(rx=(cur[0]-prev[0])/dt, tx=(cur[1]-prev[1])/dt); TOT["rx"], TOT["tx"] = cur; HIST.append((ct, NOW["rx"], NOW["tx"]))
        prev, pt = cur, ct

def private(ip):
    return ip.startswith(("10.", "192.168.", "127.", "169.254.", "::1", "fe80", "100.64.", "100.65.", "100.66.", "100.67.", "100.68.", "100.69.")) or (ip.startswith("172.") and 16 <= int(ip.split(".")[1] or 0) <= 31)

def rdns(ip):
    if ip not in RDNS:
        RDNS[ip] = ""
        def look():
            try: RDNS[ip] = socket.gethostbyaddr(ip)[0]
            except Exception: pass
        threading.Thread(target=look, daemon=True).start()
    return RDNS[ip]

def conn_poller():
    """Flows opened by the board itself, named through the DNS answers it has seen."""
    global CONNS
    while not ARGS.demo:
        agg = collections.Counter(); cnt = collections.Counter(); last = None
        try:
            out = subprocess.run(["ss", "-tniH", "state", "established"], capture_output=True, text=True, timeout=5).stdout
            for l in out.splitlines():
                if l and l[0] not in " \t":
                    p = l.split(); last = p[-1].rsplit(":", 1)[0].strip("[]") if len(p) >= 4 else None
                    if last and not private(last): cnt[last] += 1
                    else: last = None
                elif last:
                    m = re.search(r"bytes_received:(\d+)", l)
                    if m: agg[last] += int(m.group(1))
        except Exception: pass
        res, t = [], time.time()
        for ip, n in cnt.most_common(12):
            host = IPMAP.get(ip) or rdns(ip) or ip
            svc, kind = classify(host)
            res.append({"ip": ip, "host": host, "service": svc, "count": n, "bytes": agg[ip]})
            if svc not in ("Other", "System"):
                with LOCK: EVENTS.append((t, "this board", host, svc, "flow" if kind in ("static", "feed", "other") else kind, False))
        with LOCK: CONNS = res
        time.sleep(4)

# ---------- demo scenario ----------
def demo():
    script = [
      ("YouTube", ["rr3---sn-p5qs7nsd.googlevideo.com", "rr5---sn-p5qlsnsl.googlevideo.com", "www.youtube.com", "i.ytimg.com", "youtubei.googleapis.com"], 26),
      (None, [], 6),
      ("TikTok", ["v16-webapp.tiktok.com", "v19.tiktokcdn-us.com", "api16-normal-useast5.tiktokv.us", "p16-sign.tiktokcdn-us.com"], 24),
      ("Google search", ["www.google.com", "www.gstatic.com", "ogs.google.com"], 10),
      ("Netflix", ["ipv4-c001-lax001-ix.1.oca.nflxvideo.net", "www.netflix.com", "occ-0-2794-2705.1.nflxso.net"], 26),
      (None, [], 5),
      ("Instagram", ["i.instagram.com", "scontent-lax3-1.cdninstagram.com", "graph.instagram.com"], 22),
    ]
    ads = ["ads.doubleclick.net", "app-measurement.com", "pixel.facebook.com", "analytics.tiktok.com", "securepubads.g.doubleclick.net"]
    while True:
        for svc, hosts, dur in script:
            end = time.time() + dur
            while time.time() < end:
                if svc and random.random() < 0.75: record("192.168.1.20", random.choice(hosts), False)
                if random.random() < (0.25 if svc else 0.08): record("192.168.1.20", random.choice(ads), True)
                if random.random() < 0.12: record("192.168.1.20", "gateway.icloud.com", False)
                if random.random() < 0.18: record("192.168.1.31", random.choice(["audio-ak-spotify-com.akamaized.net", "spclient.wg.spotify.com", "oauth.reddit.com", "i.redd.it", "events.data.microsoft.com"]), False)
                if random.random() < 0.15: record("192.168.1.44", random.choice(["mtalk.google.com", "v16-webapp.tiktok.com", "i.instagram.com", "www.google.com"]), False)
                if random.random() < 0.05: record("192.168.1.44", "ads.doubleclick.net", True)
                time.sleep(random.uniform(0.2, 0.9))

# ---------- stats ----------
HINTS = {"Apple device": ("apple.com", "icloud.com", "mzstatic.com", "apple-dns.net"),
         "Windows PC": ("msftconnecttest.com", "windowsupdate.com", "windows.com", "events.data.microsoft.com"),
         "Android phone": ("mtalk.google.com", "android.clients.google.com", "play-fe.googleapis.com")}
SPECIAL = ("Everything else", "Ads and trackers")

def build_stats():
    now = time.time(); t0 = now - NBINS * STEP
    with LOCK:
        ev = [e for e in EVENTS if e[0] >= t0]
        hist = [h for h in HIST if h[0] >= t0]
        d = dict(DNS); clients = {c for c, t in DNS["clients"].items() if now - t < 120}
        conns = list(CONNS); rx, tx = NOW["rx"], NOW["tx"]
    devs = {}
    for t, cl, dom, svc, kind, bl in ev:
        key = "Everything else" if svc in ("Other", "System") else svc
        w = 1 if key == "Ads and trackers" else (0.5 if key == "Everything else" else WEIGHT.get(kind, 0.2))
        v = devs.setdefault(cl, {"rows": {}, "tot": 0, "last": 0, "hint": collections.Counter(), "r10": 0.0, "r20": collections.Counter(), "n": 0})
        b = min(NBINS - 1, int((t - t0) / STEP))
        r = v["rows"].setdefault(key, [0.0] * NBINS); r[b] += w
        v["tot"] += w; v["n"] += 1; v["last"] = max(v["last"], t)
        if now - t <= 10: v["r10"] += w
        if now - t <= 20 and key not in SPECIAL: v["r20"][key] += w
        for label, sfx in HINTS.items():
            if dom.endswith(sfx): v["hint"][label] += 1
    out = []
    for cl, v in devs.items():
        named = [k for k, _ in sorted(((k, sum(x)) for k, x in v["rows"].items() if k not in SPECIAL), key=lambda z: -z[1])][:4]
        order = named + [k for k in SPECIAL if k in v["rows"]]
        label = v["hint"].most_common(1)[0][0] if v["hint"] else "Device"
        if cl == "this board": label = "This board"
        top = v["r20"].most_common(1)
        out.append({"id": cl, "label": label, "last": v["last"], "lookups": v["n"], "rate": round(v["r10"], 1),
                    "now": top[0][0] if top and top[0][1] >= 1 else None,
                    "rows": [{"service": k, "v": [round(x, 1) for x in v["rows"][k]]} for k in order]})
    out.sort(key=lambda z: (z["id"] == "this board", z["id"]))
    line = [0.0] * NBINS; cnt = [0] * NBINS
    for t, r, x in hist:
        b = min(NBINS - 1, int((t - t0) / STEP)); line[b] += r + x; cnt[b] += 1
    line = [(v / c if c else 0) for v, c in zip(line, cnt)]; mx = max(line) or 1
    board = next((o for o in out if o["id"] == "this board"), None)
    if not board:
        board = {"id": "this board", "label": "This board", "last": now, "lookups": 0, "rate": 0, "now": None, "rows": []}; out.append(board)
    board["rows"].append({"service": "Connection", "line": True, "v": [round(x / mx, 3) for x in line]})
    # what is happening now (all devices)
    cand = collections.defaultdict(lambda: {"score": 0.0, "video": 0, "audio": 0, "search": 0, "doms": collections.Counter(), "vdoms": collections.Counter(), "last": 0})
    for t, cl, dom, svc, kind, bl in ev:
        if bl or svc in ("Other", "System", "Ads and trackers"): continue
        age = now - t; c = cand[svc]
        if age <= 120 and kind in ("video", "audio"): c[kind] += 1; c["vdoms"][dom] += 1; c["last"] = max(c["last"], t)
        if age <= 45: c["score"] += WEIGHT.get(kind, .2); c["doms"][dom] += 1 if kind not in ("video", "audio") else 0; c["last"] = max(c["last"], t)
        if age <= 45 and kind == "search": c["search"] += 1
    mode = svc = None; win = 45; best = None
    vids = [(c["video"] + c["audio"], c["last"], s) for s, c in cand.items() if c["video"] + c["audio"] > 0]
    if vids:
        best = max(vids)[2]; svc = best; mode = "video" if cand[best]["video"] >= cand[best]["audio"] else "audio"; win = 120
    else:
        sc = [(c["score"], c["last"], s) for s, c in cand.items() if c["score"] >= 1.5]
        if sc: best = max(sc)[2]; svc = best; mode = "search" if cand[best]["search"] else "browsing"
    src = "vdoms" if mode in ("video", "audio") else "doms"
    evidence = [{"domain": k, "count": v} for k, v in cand[best][src].most_common(3)] if best else []
    recent = [{"t": e[0], "client": e[1], "domain": e[2], "service": e[3], "blocked": e[5]} for e in ev[-24:]][::-1]
    return {"host": socket.gethostname(), "demo": ARGS.demo, "uptime": now - START, "t0": t0, "step": STEP,
            "dns": {"enabled": d["enabled"] or ARGS.demo, "total": d["total"], "blocked": d["blocked"], "clients": len(clients),
                    "upstream": ("demo" if ARGS.demo else "plain" if ARGS.no_tls else "mixed" if d["plain"] and d["tls"] else "plain" if d["plain"] else "tls" if d["tls"] else "idle")},
            "now": {"service": svc, "mode": mode, "window": win, "evidence": evidence},
            "devices": out, "rx": rx, "tx": tx, "recent": recent, "conns": conns[:6]}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.startswith("/api/stats"): body, ct = json.dumps(build_stats()).encode(), "application/json"
        else: body, ct = open(os.path.join(HERE, "dashboard.html"), "rb").read(), "text/html; charset=utf-8"
        self.send_response(200); self.send_header("Content-Type", ct); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--dns", action="store_true", help="run the DNS listener and ad blocker (root)")
    ap.add_argument("--dns-port", type=int, default=53)
    ap.add_argument("--bind", default="0.0.0.0", help="address for the DNS listener (use the board's IP)")
    ap.add_argument("--upstream", default="1.1.1.1")
    ap.add_argument("--ttl", type=int, default=30, help="cap answer TTL in seconds so devices re-ask often (0 = off)")
    ap.add_argument("--update-blocklist", action="store_true")
    ap.add_argument("--no-tls", action="store_true", help="send upstream lookups in the clear (default: DNS over TLS)")
    ap.add_argument("--strict", action="store_true", help="never fall back to plain DNS if TLS fails")
    ap.add_argument("--tls-port", type=int, default=853)
    ap.add_argument("--tls-name", default="cloudflare-dns.com", help="certificate name of the upstream")
    ap.add_argument("--tls-cafile", default=None, help="extra CA file (testing)")
    ap.add_argument("--demo", action="store_true")
    ARGS = ap.parse_args()
    threading.Thread(target=sampler, daemon=True).start()
    threading.Thread(target=conn_poller, daemon=True).start()
    if ARGS.demo:
        load_blocklist(False); threading.Thread(target=demo, daemon=True).start()
    if ARGS.dns:
        load_blocklist(ARGS.update_blocklist)
        threading.Thread(target=dns_server, args=(ARGS.dns_port, ARGS.upstream, ARGS.ttl, ARGS.bind), daemon=True).start()
    print("dashboard: http://0.0.0.0:%d" % ARGS.port)
    ThreadingHTTPServer(("0.0.0.0", ARGS.port), H).serve_forever()
