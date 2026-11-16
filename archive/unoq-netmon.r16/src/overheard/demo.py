"""Scripted fake traffic so the dashboard can be previewed anywhere."""
import random
import time

SCRIPT = [
    ("YouTube", ["rr3---sn-p5qs7nsd.googlevideo.com", "rr5---sn-p5qlsnsl.googlevideo.com", "www.youtube.com", "i.ytimg.com", "youtubei.googleapis.com"], 26),
    (None, [], 6),
    ("TikTok", ["v16-webapp.tiktok.com", "v19.tiktokcdn-us.com", "api16-normal-useast5.tiktokv.us", "p16-sign.tiktokcdn-us.com"], 24),
    ("Google search", ["www.google.com", "www.gstatic.com", "ogs.google.com"], 10),
    ("Netflix", ["ipv4-c001-lax001-ix.1.oca.nflxvideo.net", "www.netflix.com", "occ-0-2794-2705.1.nflxso.net"], 26),
    (None, [], 5),
    ("Instagram", ["i.instagram.com", "scontent-lax3-1.cdninstagram.com", "graph.instagram.com"], 22),
]
ADS = ["ads.doubleclick.net", "app-measurement.com", "pixel.facebook.com", "analytics.tiktok.com", "securepubads.g.doubleclick.net"]


def tick(state, svc, hosts, rng=random):
    """One step of the scenario: lookups from three fake devices."""
    if svc and rng.random() < 0.75:
        state.record("192.168.1.20", rng.choice(hosts), False)
    if rng.random() < (0.25 if svc else 0.08):
        state.record("192.168.1.20", rng.choice(ADS), True)
    if rng.random() < 0.12:
        state.record("192.168.1.20", "gateway.icloud.com", False)
    if rng.random() < 0.18:
        state.record("192.168.1.31", rng.choice(["audio-ak-spotify-com.akamaized.net", "spclient.wg.spotify.com", "oauth.reddit.com", "i.redd.it", "events.data.microsoft.com"]), False)
    if rng.random() < 0.15:
        state.record("192.168.1.44", rng.choice(["mtalk.google.com", "v16-webapp.tiktok.com", "i.instagram.com", "www.google.com"]), False)
    if rng.random() < 0.05:
        state.record("192.168.1.44", "ads.doubleclick.net", True)
    if rng.random() < 0.02:
        state.note_refused("203.0.113.7")       # a stranger knocking, so the demo shows the refused list
    if rng.random() < 0.004:
        state.record("192.168.1.44", "demo-site.xxx", True, adult=True)


def run(state):
    while True:
        for svc, hosts, dur in SCRIPT:
            end = time.time() + dur
            while time.time() < end:
                tick(state, svc, hosts)
                time.sleep(random.uniform(0.2, 0.9))
