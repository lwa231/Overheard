# Ideas for the morning review

Two ideas from tonight, reviewed against feasibility, security, effort and how they fit the existing code. Nothing here is built yet. Where I say "tested" I mean it; most of this is not.

(The dashboard-in-the-app plan is in `docs/app-plan.md`. If the "other earlier idea" you meant was something else, tell me and I'll add it.)

---
## A. Decrypting traffic on your own devices

**Goal.** Understand your own devices' HTTPS traffic at a deeper level than DNS allows, on your own hardware, with your consent per device.

**How it works.** A TLS-intercepting proxy (mitmproxy) on the board or the homelab. Each consenting device installs a local CA certificate and sends traffic through the proxy. The proxy sees plaintext, extracts metadata, and re-encrypts onward.

**What it gives you that DNS cannot.** Full hostnames and paths (for example which subreddit, which video category), request sizes and timing, per-app breakdown, and the ability to throttle one connection instead of one lookup.

**What it will not do.**
- Apps with certificate pinning (banking, many mobile apps) refuse to work through it. They must go on a bypass list.
- It cannot cover devices that have not installed the CA, or traffic that bypasses the proxy (VPN, DoH inside apps, QUIC unless blocked).
- It does not work on guests' or other people's devices without them installing the CA, and doing that without consent is not OK.

**Risks, ranked.**
1. The CA private key is the crown jewel. Anyone who gets it can impersonate any site to every enrolled device. Mitigation: generated on the host, mode 600, never exported, never on the laptop, optional hardware-backed storage on the homelab.
2. The proxy holds plaintext, including passwords and tokens. Mitigation: store only derived metadata (host, path category, size, time), never bodies, headers, cookies or credentials; scrub in memory.
3. Proxy compromise or bug breaks TLS for enrolled devices. Mitigation: minimal exposure, no open ports to the internet, keep mitmproxy updated, run as an unprivileged user in a container.
4. Failure mode: if the proxy is down, enrolled devices lose internet. Mitigation: fail open for banking and health, clear status in the dashboard, kill switch.
5. Legal and social: fine on your own devices with your consent; not fine on anyone else's. Building-network and roommate situations need explicit opt-in per person.

**Fit with the code.** The project is stdlib-only Python. mitmproxy is a large third-party dependency, so it runs as a separate service that feeds category events into the existing `State` and `ProfileStore`. The adult guard keeps working at the DNS layer and can later get path-level signals (for example NSFW subreddits) from the proxy.

**Effort.** Roughly 2 to 4 days for a solid first version: enrollment flow, bypass list, metadata extractor, kill switch, tests. The enrollment UX (installing the CA on each OS) is the slow part.

**Decisions for you.**
- Which devices are in scope first (your Mac and phone only?)
- Run it on the UNO Q or wait for the homelab (the UNO Q is small; TLS inspection is CPU-heavy)
- Metadata only, or also keep short-lived plaintext samples for debugging (I recommend metadata only)

**Recommendation.** Do it after the homelab exists, on your own devices first, metadata-only, with a visible per-device on/off and a bypass list that ships with banking, health and password managers.

---
## B. Alexa control and homelab connectivity

**Goal.** Let you trigger a small set of preset actions by voice, and give the project a clean way to talk to a future homelab, without exposing anything to Amazon or the internet.

### B1. Alexa options

| Option | Local? | Works with stdlib-only Python? | Notes |
|---|---|---|---|
| Emulated Hue bridge | Yes (LAN) | Yes (SSDP on UDP 1900 plus an HTTP server on port 80) | Many people use it; Echo discovers it natively. Reports show Alexa needs port 80, may need the "Hue Bridge V1" discovery route, and discovery has broken for some people after Amazon changes. Port 80 needs a capability or a redirect. Treat it as best-effort, not guaranteed. |
| Matter bridge | Yes (LAN) | No. Python Matter stacks carry binary dependencies; the practical route is a separate Matter component | Amazon documents local control of Matter devices and bridged devices on supported Echos, so this is the officially supported path and will probably outlast Hue emulation. More setup. |
| Custom Alexa skill (Lambda) | No, cloud | Board stays outbound-only | Real voice phrases, but an AWS account, account linking, and a queue the board polls. More moving parts and more places for things to break. |
| Expose the dashboard to the internet | No | n/a | Rejected. |

**What Amazon sees in the local options.** Device names and on/off/level commands. It does not see DNS logs, profiles, flagged sites or traffic.

**Allow-list (what Alexa may trigger).**
- LED animation on/off, brightness, character choice
- "Quiet mode" (hide the dashboard's live list)
- Run a speed test and show the result
- Refresh blocklists

**Never exposed to Alexa.** The adult guard, SafeSearch, penalty settings, profiles, the access key, any purge or export. Anything sensitive requires an Alexa voice PIN, and I would simply not offer it.

**Security notes.** Anyone in earshot (or a TV ad) can trigger an Alexa command, so the allow-list must be harmless. Every command is logged on the board. Emulated Hue has no authentication worth the name, so it must listen only on the LAN and never on a forwarded port.

**Recommendation.** Start with the emulated Hue bridge as a small optional module, because it is local and stdlib-only. Verify on your exact Echo model before investing more. If discovery fails, move to the Matter route through the homelab (see below).

### B2. Homelab connectivity and the queue

**What the queue is for.** Decouple "something happened" from "something acts on it." Examples: Alexa asks for a speed test; the board can't do heavy work (TLS inspection, ML on profiles) so it hands jobs to the homelab; the homelab pushes results back.

**Design.**
- Board keeps a small SQLite-backed job queue (already a dependency in practice) with a strict action allow-list, a size cap and expiry.
- Transport options: MQTT broker on the homelab (simple, widely supported), or HTTP long-polling over Tailscale. All connections are outbound from the board or travel over the Tailscale tunnel. No inbound ports from the internet.
- Every job is signed (HMAC with a key stored mode 600). Unknown actions are dropped and logged.
- The homelab side can run Home Assistant; it already has an MQTT integration and a Matter bridge add-on, so it becomes the single place that talks to Alexa while the board only ever sees allow-listed jobs.

**Open question that decides the shape.** What the homelab will be (a mini PC, a Raspberry Pi, a NAS?) and whether it runs Home Assistant. If yes, the best architecture is: Alexa to Home Assistant (Matter) to MQTT to the board. If no, the emulated Hue module on the board is the lightest start.

**Effort.** Hue emulation module: about 1 day with tests. Queue plus MQTT client: about 1 to 2 days. Matter route: depends on the homelab, about 1 to 3 days.

**Risks.**
- Dependency creep. MQTT clients and Matter stacks are not stdlib. Keep them behind a clean adapter so the core stays dependency-free.
- Attack surface. Every listener is a new door. Hue emulation adds an unauthenticated HTTP port on the LAN; the queue adds a signed channel. Both are small, but they are not zero.
- Reliability. Alexa discovery is the part most likely to cause frustration, independent of our code.

---
## Questions to settle in the morning
1. Is the "other earlier idea" decryption, the app dashboard, or something else?
2. Which Echo model do you have, and is it on the same network as the board? (The building Wi-Fi's client isolation may block local discovery entirely, which would rule out the local Alexa options until the homelab and its own router exist.)
3. What is the homelab going to be, and when?
4. Decryption: your own devices only, first on the Mac and phone?
5. Do you want the Alexa module built before the homelab, or wait?
