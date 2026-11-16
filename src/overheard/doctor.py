"""Phone test, run on the board: did a lookup of phonetest.example.com reach Overheard, and was it answered?
    python3 -m overheard.doctor [--seconds 90]
Polls the local dashboard API (with the access token from the data dir) while you open that name on the phone."""
import argparse
import json
import os
import time
import urllib.request

from . import auth

DOMAIN = "phonetest.example.com"


def verdict(stats, domain, since, seen):
    """One /api/stats payload -> (answered_from, refused_from). `seen` maps address -> refusal count before the test."""
    hit = [e["client"] for e in stats.get("recent", []) if e["domain"].rstrip(".").lower() == domain and e["t"] >= since]
    refused = [r["id"] for r in stats.get("refused", []) if r["count"] > seen.get(r["id"], 0)]
    return (hit[0] if hit else None), refused


def fetch(url, token):
    req = urllib.request.Request(url, headers={"Cookie": "%s=%s" % (auth.COOKIE, token), "X-Overheard-Doctor": "1"})
    with urllib.request.urlopen(req, timeout=4) as r:
        return json.load(r)


def run(url, token, domain, seconds, say=print, sleep=time.sleep, clock=time.time):
    since = clock()
    seen = {r["id"]: r["count"] for r in fetch(url, token).get("refused", [])}
    say("Waiting up to %d s. On the phone, open  http://%s  (it will not load, that is fine)." % (seconds, domain))
    refused_all = []
    while clock() - since < seconds:
        answered, refused = verdict(fetch(url, token), domain, since, seen)
        for ip in refused:
            if ip not in refused_all:
                refused_all.append(ip)
                say("  refused: a lookup from %s was turned away (its address is not in the allowed networks)" % ip)
        if answered:
            say("ANSWERED from %s: the phone reaches the board and gets answers." % answered)
            return 0
        sleep(1)
    if refused_all:
        say("REFUSED from %s: the board saw the phone but its address is not allowed. Re-run the install with ALLOW_EXTRA=%s" % (", ".join(refused_all), refused_all[0] + ("/128" if ":" in refused_all[0] else "/32")))
        return 1
    say("NEVER ARRIVED: nothing from the phone reached the board. Check the phone's DNS setting (Manual, one of the board's addresses), "
        "Private DNS / Private Relay off, and that the Wi-Fi network lets devices talk to each other.")
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="overheard.doctor", description=__doc__)
    ap.add_argument("--seconds", type=int, default=90)
    ap.add_argument("--domain", default=DOMAIN)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--data-dir", default=os.path.expanduser("~/netmon/data"))
    a = ap.parse_args(argv)
    try:
        token = open(os.path.join(a.data_dir, "token")).read().strip()
    except OSError:
        print("No access token in %s: is Overheard installed and started?" % a.data_dir)
        return 2
    try:
        return run("http://127.0.0.1:%d/api/stats" % a.port, token, a.domain.lower(), a.seconds)
    except OSError as e:
        print("Overheard is not answering on 127.0.0.1:%d (%s). Run Check Overheard." % (a.port, e))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
