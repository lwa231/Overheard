"""Turn raw state into the JSON the dashboard draws."""
import collections
import socket

from .fingerprint import identify
from .services import WEIGHT
from .state import NBINS, STEP

SPECIAL = ("Everything else", "Ads and trackers", "Adult content")


def _devices(ev, now, t0):
    devs = {}
    for t, cl, dom, svc, kind, _bl in ev:
        key = "Everything else" if svc in ("Other", "System") else svc
        w = 1 if key in ("Ads and trackers", "Adult content") else (0.5 if key == "Everything else" else WEIGHT.get(kind, 0.2))
        v = devs.setdefault(cl, {"rows": {}, "last": 0, "names": set(), "r10": 0.0, "r20": collections.Counter(), "n": 0})
        b = min(NBINS - 1, int((t - t0) / STEP))
        v["rows"].setdefault(key, [0.0] * NBINS)[b] += w
        v["n"] += 1
        v["last"] = max(v["last"], t)
        if now - t <= 10:
            v["r10"] += w
        if now - t <= 20 and key not in SPECIAL:
            v["r20"][key] += w
        if len(v["names"]) < 400:
            v["names"].add(dom)
    out = []
    for cl, v in devs.items():
        named = [k for k, _ in sorted(((k, sum(x)) for k, x in v["rows"].items() if k not in SPECIAL), key=lambda z: -z[1])][:4]
        order = named + [k for k in SPECIAL if k in v["rows"]]
        fp = identify(v["names"])
        label = fp["label"]
        if cl == "this board":
            label = "This board"
        top = v["r20"].most_common(1)
        out.append({"id": cl, "label": label, "confidence": fp["confidence"], "evidence": fp["evidence"], "shared": fp["shared"], "last": v["last"], "lookups": v["n"], "rate": round(v["r10"], 1),
                    "now": top[0][0] if top and top[0][1] >= 1 else None,
                    "rows": [{"service": k, "v": [round(x, 1) for x in v["rows"][k]]} for k in order]})
    out.sort(key=lambda z: (z["id"] == "this board", z["id"]))
    return out


def _now_playing(ev, now):
    cand = collections.defaultdict(lambda: {"score": 0.0, "video": 0, "audio": 0, "search": 0,
                                            "doms": collections.Counter(), "vdoms": collections.Counter(), "last": 0})
    for t, _cl, dom, svc, kind, bl in ev:
        if bl or svc in ("Other", "System", "Ads and trackers", "Adult content"):
            continue
        age, c = now - t, cand[svc]
        if age <= 120 and kind in ("video", "audio"):
            c[kind] += 1
            c["vdoms"][dom] += 1
            c["last"] = max(c["last"], t)
        if age <= 45:
            c["score"] += WEIGHT.get(kind, .2)
            if kind not in ("video", "audio"):
                c["doms"][dom] += 1
            c["last"] = max(c["last"], t)
            if kind == "search":
                c["search"] += 1
    mode = svc = best = None
    win = 45
    vids = [(c["video"] + c["audio"], c["last"], s) for s, c in cand.items() if c["video"] + c["audio"] > 0]
    if vids:
        best = svc = max(vids)[2]
        mode = "video" if cand[best]["video"] >= cand[best]["audio"] else "audio"
        win = 120
    else:
        sc = [(c["score"], c["last"], s) for s, c in cand.items() if c["score"] >= 1.5]
        if sc:
            best = svc = max(sc)[2]
            mode = "search" if cand[best]["search"] else "browsing"
    src = "vdoms" if mode in ("video", "audio") else "doms"
    evidence = [{"domain": k, "count": n} for k, n in cand[best][src].most_common(3)] if best else []
    return {"service": svc, "mode": mode, "window": win, "evidence": evidence}


def _upstream_state(cfg, d):
    if cfg.demo:
        return "demo"
    if cfg.no_tls:
        return "plain"
    if d["plain"] and d["tls"]:
        return "mixed"
    return "plain" if d["plain"] else "tls" if d["tls"] else "idle"


def build_stats(state, cfg, guard=None, vitals=None):
    now = state.clock()
    t0 = now - NBINS * STEP
    with state.lock:
        ev = [e for e in state.events if e[0] >= t0]
        hist = [h for h in state.hist if h[0] >= t0]
        d = dict(state.dns)
        clients = {c for c, t in state.dns["clients"].items() if now - t < 120}
        conns = list(state.conns)
        rx, tx = state.now["rx"], state.now["tx"]
        refused = sorted(({"id": ip, "count": c, "last": t} for ip, (c, t) in state.refused.items()), key=lambda r: -r["last"])[:12]
    out = _devices(ev, now, t0)
    line, cnt = [0.0] * NBINS, [0] * NBINS
    for t, r, x in hist:
        b = min(NBINS - 1, int((t - t0) / STEP))
        line[b] += r + x
        cnt[b] += 1
    line = [(v / c if c else 0) for v, c in zip(line, cnt, strict=True)]
    mx = max(line) or 1
    board = next((o for o in out if o["id"] == "this board"), None)
    if not board:
        board = {"id": "this board", "label": "This board", "last": now, "lookups": 0, "rate": 0, "now": None, "rows": []}
        out.append(board)
    board["rows"].append({"service": "Connection", "line": True, "v": [round(x / mx, 3) for x in line]})
    recent = [{"t": e[0], "client": e[1], "domain": e[2], "service": e[3], "blocked": e[5]} for e in ev[-24:]][::-1]
    return {"host": socket.gethostname(), "demo": cfg.demo, "uptime": now - state.started, "t0": t0, "step": STEP,
            "dns": {"enabled": d["enabled"] or cfg.demo, "total": d["total"], "blocked": d["blocked"],
                    "clients": len(clients), "upstream": _upstream_state(cfg, d)},
            "adult": guard.summary() if guard else {"enabled": False, "slowed": [], "flagged": 0, "listed": 0},
            "now": _now_playing(ev, now), "devices": out, "rx": rx, "tx": tx, "recent": recent, "conns": conns[:6],
            "refused": refused, "net": dict(vitals.net) if vitals else {},
            "sys": vitals.snapshot() if vitals else {}}
