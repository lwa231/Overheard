"""Ad and tracker domain list (StevenBlack hosts), matched on every parent domain."""
import os
import urllib.request

URL = "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts"
MAX_BYTES = 20 << 20


BUILTIN_AD_DOMAINS = {
    "googleads.g.doubleclick.net",
    "ad.doubleclick.net",
    "cm.g.doubleclick.net",
    "static.doubleclick.net",
    "stats.g.doubleclick.net",
    "securepubads.g.doubleclick.net",
    "pubads.g.doubleclick.net",
    "adservice.google.com",
    "pagead2.googlesyndication.com",
    "tpc.googlesyndication.com",
    "partner.googlesyndication.com",
    "ad.youtube.com",
    "ads.youtube.com",
    "s.youtube.com",
}


class Blocklist:
    def __init__(self, domains=()):
        self.domains = set(domains) | BUILTIN_AD_DOMAINS

    def __len__(self):
        return len(self.domains)

    def is_blocked(self, name):
        p = name.lower().rstrip(".").split(".")
        return any(".".join(p[k:]) in self.domains for k in range(len(p) - 1))

    @classmethod
    def load(cls, path, update=False, log=print):
        if update or not os.path.exists(path):
            try:
                data = urllib.request.urlopen(URL, timeout=25).read(MAX_BYTES).decode()
                doms = {ln.split()[1].lower() for ln in data.splitlines()
                        if ln.startswith("0.0.0.0 ") and len(ln.split()) > 1 and ln.split()[1] != "0.0.0.0"}
                os.makedirs(os.path.dirname(path), exist_ok=True)
                tmp = path + ".tmp"
                with open(tmp, "w") as f:
                    f.write("\n".join(sorted(doms)))
                os.replace(tmp, path)
            except Exception as e:
                log("blocklist download failed: %s" % e)
        bl = cls()
        if os.path.exists(path):
            with open(path) as f:
                bl.domains.update(x.strip().lower() for x in f if x.strip())
        return bl
