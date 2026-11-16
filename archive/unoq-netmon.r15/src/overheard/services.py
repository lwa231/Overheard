"""Which service a hostname belongs to. DNS reveals the service, never the content."""
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
# how much each kind of lookup says "someone is actively using this"
WEIGHT = {"video": 3, "audio": 2, "search": 2.5, "media": 1.5, "feed": 1, "static": 0.3, "flow": 1, "system": 0, "other": 0.2, "ads": 0, "adult": 0}

_RULES, _EXACT = {}, {}
for _svc, _kinds in SERVICES.items():
    for _kind, _sfx in _kinds.items():
        for _s in _sfx:
            (_EXACT if _s.startswith("=") else _RULES)[_s.lstrip("=")] = (_svc, _kind)


def classify(domain):
    """Return (service, kind). Unknown hosts are ("Other", "other")."""
    d = domain.lower().rstrip(".")
    if d in _EXACT:
        return _EXACT[d]
    parts = d.split(".")
    for k in range(len(parts) - 1):
        hit = _RULES.get(".".join(parts[k:]))
        if hit:
            return hit
    return ("Other", "other")
