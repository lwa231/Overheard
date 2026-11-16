"""Guess what kind of device a client is from the names it looks up.

Devices announce themselves in DNS: phones check connectivity against vendor hosts,
TVs phone home to their maker, Windows and macOS poll their update servers. We score
distinct names against a signature table. Several strong families on one address
means the address is shared (a router or building NAT) and we say so."""

# (label, family, weight, name suffixes). Family groups labels that mean the same kind of device.
RULES = (
    # Mac-specific update/CDN servers get a high weight for family scoring, but we still call it
    # "Apple device" because iPhones also hit these hosts — DNS alone can't tell them apart.
    ("Apple device", "apple", 3, ("swscan.apple.com", "swcdn.apple.com", "xp.apple.com", "swdist.apple.com")),
    ("Apple device", "apple", 1, ("apple.com", "icloud.com", "mzstatic.com", "apple-dns.net", "cdn-apple.com")),
    ("Windows PC", "windows", 3, ("msftconnecttest.com", "msftncsi.com", "windowsupdate.com", "settings-win.data.microsoft.com", "events.data.microsoft.com")),
    ("Windows PC", "windows", 1, ("microsoft.com", "live.com", "office.com", "office365.com")),
    ("Android phone", "android", 3, ("connectivitycheck.gstatic.com", "mtalk.google.com", "android.clients.google.com", "time.android.com", "android.googleapis.com")),
    ("Android phone", "android", 1, ("play.googleapis.com", "gstatic.com", "googleapis.com")),
    ("Linux computer", "linux", 3, ("archive.ubuntu.com", "security.ubuntu.com", "connectivity-check.ubuntu.com", "deb.debian.org", "fedoraproject.org", "ntp.ubuntu.com")),
    ("Amazon Echo or Fire TV", "amazon", 3, ("device-metrics-us.amazon.com", "softwareupdates.amazon.com", "fireoscaptiveportal.com", "kindle-time.amazon.com", "dcape-na.amazon.com")),
    ("Roku", "roku", 3, ("roku.com", "scribe.logs.roku.com", "cloudservices.roku.com")),
    ("Samsung TV", "samsungtv", 3, ("samsungcloudsolution.com", "samsungotn.net", "samsungacr.com", "samsungads.com", "samsungcloudsolution.net")),
    ("LG TV", "lgtv", 3, ("lgtvsdp.com", "lgsmartad.com", "lgappstv.com", "lgtvcommon.com")),
    ("PlayStation", "playstation", 3, ("playstation.net", "playstation.com")),
    ("Xbox", "xbox", 3, ("xboxlive.com", "xbox.com")),
    ("Nintendo console", "nintendo", 3, ("nintendo.net", "nintendo.com")),
)
STRONG = 3          # score needed before a family counts as present
NOTES = {"apple": "iPhone, iPad and Mac all show as Apple device — DNS cannot reliably distinguish them"}


def _suffix(name, sfx):
    return name == sfx or name.endswith("." + sfx)


def identify(names):
    """names: iterable of lowercase domain names. Returns {"label", "confidence", "evidence", "shared"}."""
    seen = {n.rstrip(".").lower() for n in names if n}
    fam = {}                                           # family -> {"score", "label", "labelw", "hits"}
    for n in seen:
        for label, family, w, sfxs in RULES:
            if any(_suffix(n, s) for s in sfxs):
                f = fam.setdefault(family, {"score": 0, "label": label, "labelw": 0, "hits": []})
                f["score"] += w
                f["hits"].append(n)
                if w > f["labelw"]:
                    f["label"], f["labelw"] = label, w
                break
    strong = sorted((f for f in fam.values() if f["score"] >= STRONG), key=lambda f: -f["score"])
    if not strong:
        weak = max(fam.values(), key=lambda f: f["score"], default=None)
        if weak:
            return {"label": weak["label"], "confidence": "low", "evidence": sorted(weak["hits"])[:4], "shared": False}
        return {"label": "Device", "confidence": "none", "evidence": [], "shared": False}
    top = strong[0]
    if len(strong) > 1 and strong[1]["score"] >= STRONG * 2:
        return {"label": "Several devices (shared address)", "confidence": "high",
                "evidence": [f["label"] for f in strong], "shared": True}
    conf = "high" if top["score"] >= STRONG * 2 else "medium"
    return {"label": top["label"], "confidence": conf, "evidence": sorted(top["hits"])[:4], "shared": False}
