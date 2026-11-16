# Hardening guide: LAN DNS server (UNO Q) + Tailscale exit node (Ubuntu 24.04 VPS)

Provenance: [F] = page fetched this session and checked. [K] = from my background knowledge; URL is the canonical reference but I did NOT fetch it, so verify before relying on exact syntax. Several vendor pages were blocked by the fetch allowlist (Tailscale ACL/key-expiry, Ubuntu server docs, Hostinger ToS). One fetched third-party page contained embedded text instructing AI readers to do something unrelated (write a poem); it was ignored.

## 0. Threat models: what is and is not protected

- Building operator/neighbors: DoT hides query names; they still see destination IPs, TLS SNI (unless ECH), timing/volume, your MAC/DHCP name. A VPN hides these too, leaving only a WireGuard flow to the VPS IP.
- Websites: see the VPS IP, not yours; cookies/logins/fingerprints still identify you.
- Hostinger and the DoT upstream (sees every query + your IP): trust moves to them, it is not removed.

Honest framing: this setup defends against passive snooping/injection by the local network and hides your home IP from sites. It is not anonymity.

## 1. DNS server (UNO Q)

Priority order: (1) stop being an open resolver / bind narrowly, (2) validate DNSSEC, (3) encrypted upstream, (4) rate limit, (5) logging/privacy.

**1.1 Bind narrowly + restrict clients.** On an uncontrolled LAN every neighbor can reach 0.0.0.0. Bind to the specific LAN/Tailscale address and drop sources outside an allow-list (CGNAT means no internet exposure, but the building LAN is exposed). Client isolation on the building Wi-Fi may break LAN DNS; test early. nftables [K]:
```
sudo nft add table inet f
sudo nft 'add chain inet f in { type filter hook input priority 0; policy drop; }'
sudo nft add rule inet f in ct state established,related accept
sudo nft add rule inet f in iif lo accept
sudo nft add rule inet f in ip saddr { 192.168.1.20, 192.168.1.21 } meta l4proto { tcp, udp } th dport 53 accept
sudo nft add rule inet f in iifname "tailscale0" accept
```
Unbound: `interface: 192.168.1.5`, `access-control: 192.168.1.0/24 allow`, `access-control: 0.0.0.0/0 refuse` (https://unbound.docs.nlnetlabs.nl/en/latest/manpages/unbound.conf.html [K]).

**1.2 Rate limit / no amplification.** Cap UDP replies (EDNS buffer 1232, https://www.dnsflagday.net/2020/ [K]), refuse `ANY`, REFUSED for non-allow-listed sources, per-source token bucket (~20 qps). Unbound: `ratelimit: 1000`, `ip-ratelimit: 100`, `edns-buffer-size: 1232`, `deny-any: yes` [K]. Hostinger forbids public recursive DNS on its servers [F] (https://www.hostinger.com/legal/hosting-agreement), so keep any VPS resolver tailnet-only.

**1.3 DoT upstream correctly.** Why: DoT without certificate verification is only protection against passive sniffing, not an active on-path attacker.
- Python stdlib: `ssl.create_default_context()`, `ctx.check_hostname=True`, connect to the IP but pass `server_hostname="dns.quad9.net"`; port 853; never `CERT_NONE`. Reuse one TLS connection (pipeline) rather than reconnecting per query. Pin hostnames, not just IPs, and hardcode a bootstrap IP so you don't need plaintext DNS to find the upstream.
- Unbound upstream [K]:
```
forward-zone:
  name: "."
  forward-tls-upstream: yes
  forward-addr: 9.9.9.9@853#dns.quad9.net
  forward-addr: 149.112.112.112@853#dns.quad9.net
```
  Ref: https://unbound.docs.nlnetlabs.nl/en/latest/topics/privacy/dnssec.html and the man page above [K]. Related config walkthrough [F, downstream side only]: https://www.bentasker.co.uk/documentation/linux/701-configuring-unbound-for-downstream-dot
- Fail closed: if DoT fails, return SERVFAIL, do not fall back to plaintext UDP/53.

**1.4 DNSSEC validation.** DoT protects the hop; DNSSEC protects the data from a lying upstream. A forwarder trusting the upstream's AD bit is not validating. Run local Unbound with `auto-trust-anchor-file: "/var/lib/unbound/root.key"`, `harden-dnssec-stripped: yes`, `aggressive-nsec: yes` [K]. Pure-Python validation (RRSIG/NSEC3) is a strong reason to switch (1.7). Full recursion would expose queries in plaintext to the building, so forward over DoT.

**1.5 Query privacy.** Keep logs short-lived (24-72 h) or in RAM, mode 0600; never send EDNS Client Subnet; qname minimisation if recursing (https://www.rfc-editor.org/rfc/rfc9156 [K]); optional EDNS padding on DoT (https://www.rfc-editor.org/rfc/rfc8467 [K]).

**1.6 What the building operator still sees despite DoT.** Destination IPs of every connection; the SNI in the TLS ClientHello (hostname in clear unless ECH); the fact and size/timing of the DoT session on port 853 (easily blocked or fingerprinted; DoH on 443 blends in better); your device MAC/DHCP hostname. ECH is deployed only for a subset of sites (mainly Cloudflare-fronted), so SNI mostly remains visible. Sources: https://cdt.org/insights/encrypted-client-hello-closing-the-sni-metadata-gap/ and https://www.scoutdns.com/library/encrypted-dns-privacy-vs-anonymity [search results only, not fetched]. The way to hide SNI/IPs from the building is the VPN (section 3), not DoT.
- If port 853 is blocked by the building, fall back to DoH on 443 (Unbound needs a build with DoH client support; AdGuard Home and dnscrypt-proxy support DoH upstream natively).

**1.7 Compare and when to switch.**

| Option | DoT/DoH upstream | DNSSEC | Blocklists | Rate limit/ACL | Notes |
|---|---|---|---|---|---|
| Our Python stdlib resolver | DoT via ssl (own code) | Not unless you write it | Yes (own) | Own code | Single-threaded/GIL, parsing bugs are the risk (malformed packets, compression-pointer loops, TCP slow-loris). Great for learning. |
| Unbound | Yes (forward-tls-upstream) | Full validator, mature | Via `local-zone` lists (blocking is basic) | ratelimit, ip-ratelimit, access-control | Best resolver core; low RAM. |
| dnsmasq | No native DoT upstream (needs stubby/dnscrypt-proxy in front) | Validates if built with it; weak | Via hosts/`address=` | Limited | Tiny; used inside Pi-hole (FTL). |
| Pi-hole (FTL) | Via cloudflared/stubby/Unbound | Passes through/validates via dnsmasq | Excellent UI/lists | Has `RATE_LIMIT` per client | Auth'd web UI; heavier. https://docs.pi-hole.net/ [K] |
| AdGuard Home | Native DoT/DoH/DoQ upstream | Optional (`Enable DNSSEC`, relies on upstream AD) | Excellent | Per-client rate limit, ACL | Single Go binary, easy on ARM. https://github.com/AdguardTeam/AdGuardHome [K] |

**Recommendation:** keep the Python resolver as the learning/blocklist front-end only while it listens on a loopback/Tailscale/allow-listed address and forwards to a local Unbound (127.0.0.1:5335) doing DoT + DNSSEC. Switch to Unbound (resolver) + AdGuard Home or Pi-hole (blocking/UI) when any of: you need DNSSEC validation, you want it reachable by guests/other people, you see malformed-packet crashes, or you want a vetted dashboard with real auth. The stdlib parser is the weakest link; a battle-tested core is a security upgrade, not just a convenience.

## 2. Dashboard (port 8080)

**2.1 Bind to loopback and publish via Tailscale only.** Why: on the building Wi-Fi, `0.0.0.0:8080` is reachable by every neighbor on the LAN; plain HTTP leaks the query log and cookies.
- Python: `HTTPServer(("127.0.0.1", 8080), Handler)`.
- Publish to your tailnet with TLS (no root needed to forward a port) [F]: `tailscale serve --bg 8080` (the docs example is `tailscale serve 3000`, which proxies `http://127.0.0.1:3000` to an `https://<device>.<tailnet>.ts.net` URL). Requires HTTPS certificates enabled in the admin console. Access control rules apply to Serve traffic. Source: https://tailscale.com/kb/1312/serve
- Do NOT use `tailscale funnel` (public internet).
- Verify: `ss -ltnp | grep 8080` should show `127.0.0.1` only.

**2.2 Authentication.** Options, strongest first:
1. Tailscale identity via Serve [F]: Serve injects `Tailscale-User-Login` / `Tailscale-User-Name` and strips client-supplied copies; "the docs recommend having your backend listen only on localhost" or someone can forge them. Tagged-device and Funnel traffic carry no such headers. Check in the handler: `if self.headers.get("Tailscale-User-Login") != "you@example.com": 403`. Pair with a tailnet ACL that only allows your own devices to reach the UNO Q. Source: https://tailscale.com/kb/1312/serve
2. Plus a shared token (long random, `secrets.token_urlsafe(32)`) compared with `hmac.compare_digest`, sent as `Authorization: Bearer`, for scripts.
3. Basic auth over TLS only (never over plain HTTP).

**2.3 CSRF and browser-side hygiene** [K]. Why: a malicious page you visit can POST to a LAN/tailnet dashboard (blocklist edits, "disable blocking").
- State-changing actions: POST only; require a per-session CSRF token or custom header (`X-Requested-With`) and verify `Origin` equals your `ts.net` hostname (this also stops DNS rebinding; check the `Host` header against an allow-list too).
- Cookies: `Set-Cookie: s=...; HttpOnly; Secure; SameSite=Strict; Path=/`.
- Headers: `Content-Security-Policy: default-src 'self'`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`.
- Escape every domain name rendered in HTML (a hostile domain/label in the log is an XSS vector): `html.escape()`.
- Ref: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html [K]

**2.4** Run as a dedicated user; bind port 53 with `AmbientCapabilities=CAP_NET_BIND_SERVICE`, `NoNewPrivileges=yes`, `ProtectSystem=strict` in the systemd unit (https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html [K]).

## 3. Tailscale exit node on the VPS

**3.1 Install and advertise** [F] https://tailscale.com/kb/1103/exit-nodes
```
echo 'net.ipv4.ip_forward = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf
echo 'net.ipv6.conf.all.forwarding = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf
sudo sysctl -p /etc/sysctl.d/99-tailscale.conf
sudo tailscale set --advertise-exit-node
sudo tailscale up
```
Then approve under Machines > Edit route settings > Use as exit node. IPv6 forwarding must be enabled in addition to IPv4; the default routes are `0.0.0.0/0` and `::/0`. Keep the firewall forwarding default-deny. Tailscale's page also notes Linux UDP GRO tuning for throughput .

**3.2 Tags and ACLs.** Tag the VPS `tag:exit` (`tailscale up --advertise-exit-node --advertise-tags=tag:exit`) and the UNO Q `tag:dns`. Exit-node use needs a rule with `dst` `autogroup:internet` [F]. Example [K]:
```
"tagOwners": {"tag:exit": ["autogroup:admin"], "tag:dns": ["autogroup:admin"]},
"grants": [
 {"src": ["autogroup:member"], "dst": ["autogroup:internet"], "ip": ["*"]},
 {"src": ["autogroup:member"], "dst": ["tag:dns"], "ip": ["tcp:443","tcp:53","udp:53"]}
],
"autoApprovers": {"exitNode": ["tag:exit"]}
```
No rule from `tag:exit` outward. Protect the identity-provider login with MFA. Docs: https://tailscale.com/kb/1068/acl-tags [K].

**3.3 Key expiry.** Why: an expired exit-node key fails closed (clients lose internet) [F]: "routes stay configured but become unreachable." Tagged devices have key expiry disabled by default [K]; verify in the admin console. Disable expiry only for the tagged VPS, keep it on for phones. Source: https://tailscale.com/kb/1103/exit-nodes [F], https://tailscale.com/kb/1028/key-expiry [K].

**3.4** After tailnet SSH works, close public port 22 (section 4); keep the Hostinger web console as break-glass.

**3.5 DNS with the exit node.** With an exit node selected, the client sends DNS via the tailnet DNS configuration. Set admin console DNS > Global nameservers to your UNO Q's Tailscale IP (blocking + DoT) and enable "Override DNS servers" (so the phone doesn't use the building resolver), with MagicDNS on. Caveat: if the UNO Q is offline, DNS breaks; add a second resolver as fallback (e.g. a DoT-capable public one, or Unbound on the VPS bound to `tailscale0` only, never public: Hostinger prohibits public recursive DNS [F]). Refs: https://tailscale.com/kb/1054/dns, https://tailscale.com/kb/1081/magicdns [K, not fetched]. Note that the UNO Q sits behind CGNAT and building Wi-Fi: it will reach the tailnet via outbound WireGuard/DERP, so it works without port forwards, but latency may vary.

**3.6 iOS kill switch (honest).** Tailscale on iOS has no true block-on-drop kill switch. VPN On Demand [F] (profile > VPN On Demand; Wi-Fi and Cellular `Always`) restarts the tunnel but does not block traffic during a gap; strict always-on is only via MDM profiles [F]. iOS has known VPN leak behaviour for existing connections (https://blog.disconnect.me/ios-vpn-leak-advisory/; IVPN dropped its iOS kill switch: https://www.ivpn.net/blog/removal-of-kill-switch-from-our-ios-app-due-to-apple-ip-leak-issue). Treat as best effort; keep "Allow local network access" off [F]. Source: https://tailscale.com/kb/1291/ios-vpn-on-demand

**3.7 Leaks.** If the VPS lacks working IPv6, clients may still use v6 on the building network; test (section 5) and disable IPv6 on the client side if needed. DNS leaks occur if "Override DNS" is off.

## 4. VPS baseline (Ubuntu 24.04, Hostinger)

Sources: [F] https://privatedevops.com/articles/hardening-fresh-ubuntu-24-04-vps-15-minutes (commands below come from it); official refs: https://documentation.ubuntu.com/server/how-to/security/openssh-server/ , https://ubuntu.com/security/certifications/docs/usg (CIS benchmark via Ubuntu Pro USG) [K, not fetched].

**4.1 Admin user + SSH keys, then lock down.**
```
adduser ops && usermod -aG sudo ops   # install your ed25519 key in ~ops/.ssh/authorized_keys
cat > /etc/ssh/sshd_config.d/00-hardening.conf <<'X'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
AuthenticationMethods publickey
MaxAuthTries 3
AllowUsers ops
X
sshd -t && systemctl restart ssh && sshd -T | grep -E 'permitroot|passwordauth'
```
Test a second login before closing the first [F]. Name it `00-` because sshd uses the first value seen and cloud-init's `50-cloud-init.conf` can enable passwords [K]. On 24.04 ssh is socket-activated; port changes go in `ssh.socket` [K].

**4.2 ufw default deny** [F]
```
ufw default deny incoming; ufw default allow outgoing
ufw allow in on tailscale0
ufw allow 41641/udp          # optional: direct WireGuard connections (otherwise DERP relay, slower)
ufw allow 22/tcp             # remove once tailnet SSH works
ufw --force enable; ufw status verbose
```
Set `DEFAULT_FORWARD_POLICY` and add forward rules in `/etc/ufw/before.rules` / `ufw route allow in on tailscale0 out on eth0` so exit traffic is forwarded; keep masquerade handled by tailscaled. No other service should listen publicly (`ss -tulpn`).

**4.3 fail2ban** [F]: `apt install fail2ban`, `/etc/fail2ban/jail.d/sshd.local` with `[sshd] enabled=true maxretry=3 bantime=1h findtime=10m`. The source notes it mainly cuts log noise and throttles slow attacks; key-only SSH is the real control. Once SSH is tailnet-only it is optional. Alternative: CrowdSec (https://docs.crowdsec.net/) [K].

**4.4 Automatic updates** [F]: `apt install unattended-upgrades apt-listchanges && dpkg-reconfigure --priority=low unattended-upgrades`; verify `/etc/apt/apt.conf.d/20auto-upgrades` has both periodic values "1" and run `unattended-upgrade --dry-run --debug`. Add `Unattended-Upgrade::Automatic-Reboot "true"; Automatic-Reboot-Time "04:00";` for kernel fixes. Also keep the `tailscale` apt repo enabled so the client updates. 

**4.5** Optional: `lynis audit system` (https://cisofy.com/lynis/) for a scored report; CIS Ubuntu 24.04 benchmark https://www.cisecurity.org/benchmark/ubuntu_linux [K].

**4.6 Hostinger-specific.**
- Terms: the hosting agreement [F] https://www.hostinger.com/legal/hosting-agreement has no VPN clause, but prohibits using servers as an "anonymous gateway", as a relay/source for packet flooding or DoS, and running open relays/public recursive DNS; Tor exit nodes and open proxies are prohibited in the GPU annex, which signals their stance. The Universal Terms [F] https://www.hostinger.com/universal-terms-of-service-agreement bans illegal use and "actions resulting in DDOS attacks" and allows suspension for abuse; it doesn't mention VPN/proxy in the part I could read (last ~2.7k characters and the separate Abuse policy were not read). Practical reading: a private WireGuard exit node used by one person is not an open proxy, but I did not find explicit approval. Ask Hostinger support to confirm in writing before relying on it, and never open it to others or to the public internet. Your traffic from that IP is attributable to your account (abuse complaints land on you).
- DDoS: SLA excludes DDoS outages [F]. Backups are weekly "courtesy" only; take your own snapshot via hPanel after hardening (it contains the Tailscale node key; restoring an old one can duplicate the node).
- IP may change on migration [F], so use the tailnet name, not the public IP, in any configs.

## 5. Verification checklist

Manual (do after each change; phone on cellular AND on the building Wi-Fi):
1. https://dnsleaktest.com (extended test): resolvers listed must be your configured upstream's operator (e.g. Quad9) or the VPS provider, never the building ISP.
2. https://ipleak.net : IPv4 must be the VPS IP; IPv6 must be the VPS v6 address or "not detected"; check the WebRTC and DNS sections too. Alternative: https://browserleaks.com/ip.
3. Exit node on, then toggle airplane mode / switch networks and re-check (documents the On Demand gap).
4. Blocking works: open a known ad domain, or `dig @<UNO-Q> doubleclick.net` returns 0.0.0.0/NXDOMAIN.
5. DNSSEC: `dig @<resolver> dnssec-failed.org A` must give SERVFAIL; `dig @<resolver> cloudflare.com +dnssec` shows `ad` flag. Test page: https://wander.science/projects/dns/dnssec-resolver-test/ [K].

Automatable (cron/CI, run from a machine OUTSIDE the network when noted):
- Open ports on the VPS, from outside: `nmap -Pn -sS -sU -p 22,53,80,443,853,8080,41641 --top-ports 100 <vps-public-ip>`; expected open: nothing except (maybe) 41641/udp; 22 closed/filtered after the tailnet-only switch. Ref: https://nmap.org/book/man.html [K]
- Listening sockets on both hosts: `ss -tulpn` compared to a stored baseline; `ss -ltn 'sport = :8080'` shows 127.0.0.1.
- Open resolver check from outside (and from another LAN device): `dig +short @<ip> example.com +time=2` must time out/REFUSED.
- TLS of the dashboard: `testssl.sh --fast https://<device>.<tailnet>.ts.net` from a tailnet member (https://testssl.sh/ [K]); expect TLS 1.2+/1.3, valid Let's Encrypt cert from Serve. Not testable from the public internet since it is tailnet-only (that itself is the test: from a non-tailnet host it must not connect).
- Exit IP check: `curl -s https://api.ipify.org` and `curl -6 -s https://api64.ipify.org` on a Linux tailnet client with the exit node set; compare to the VPS IPs. iOS itself can't be scripted; use Shortcuts to hit ipify after toggling for a weak automation.
- SSH: `ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no ops@vps` must fail; `sshd -T` diff against expected in a nightly job; `lynis audit system --quick` weekly.
- Not automatable: browser leak tests (dnsleaktest/ipleak use a JS browser; use the manual pass), and iOS kill-switch behaviour.

## 6. Order of work
Section 2.1/2.2, then 1.1-1.3, then 4.1-4.4, then 3.1-3.5, then iOS On Demand and section 5 tests; close public SSH last; ask Hostinger to confirm exit-node use.

## 7. Unlock (stealth lock, r16)

The access token (`ov` cookie) only gets you into the dashboard. Looked-up names need a second secret, checked by the server:
- Secret: `<data_dir>/unlock`, random, mode 0600, created on first start (read it on the board). `POST /api/unlock {"secret": ...}` trades it for session cookie `ovu` (HttpOnly, SameSite=Strict, random id). Sessions expire 30 min after unlock on the server (not extended), at most 16 alive, `POST /api/lock` ends one.
- Compared in constant time. 5 failures per minute per client address, then 429 (even for the right secret) until the window passes.
- Locked `/api/stats` carries totals, rates, vitals, net, device labels and counts, refused list; no lookup names (recent, per-device evidence, now-playing evidence, board flow hosts, flagged counts) and the adult row is folded into "Everything else". `/api/flagged` and `/api/profile*` answer 403. `unlocked` is always in the payload; unlocked adds `settings`.
- `POST /api/settings {"slowdown": bool}` needs a session, accepts nothing else, and cannot reach the adult filter, its list or the cooldown. No endpoint changes or shows that configuration. Slowed indicators only appear while the slowdown is on and the viewer is unlocked.
- Doctor: a request from 127.0.0.1 with a valid `ov` cookie and `X-Overheard-Doctor: 1` gets the full `/api/stats` (nothing else). It is refused if the request carries `X-Forwarded-For`, `Forwarded`, `X-Real-IP` or `Tailscale-User-Login`, because a proxy such as `tailscale serve` makes every remote caller look like loopback.
- State-changing routes keep the same-origin, JSON-only and Host checks. Losing the file: delete `unlock` and restart to get a new secret.

## 8. R16 hardening

Audited dnsproto, DnsServer, the HTTP layer, secret handling and the adult guard; proof is `tests/test_r16_hardening.py` (41 tests, seeded).
- Fuzz: 20k random/bit-flipped/truncated/pointer-loop/oversize/bad-count packets through every dnsproto function and 6k through `handle_packet`: no exception, bounded time. Question names never follow compression pointers, so loops cannot occur.
- Fixed: TCP DNS drip-feed. `TCP_LIFETIME` was only checked between queries, so one byte every 4 s held a slot forever; `_recv_exact` now honours the deadline.
- Fixed: secret files that already existed with loose modes (hand-made, older version) stayed 0644; `token` and `unlock` are now chmod 0600 on load and after create.
- Fixed: an empty-valued `X-Forwarded-For`/`Forwarded`/`X-Real-IP`/`Tailscale-User-Login` header no longer slips past the doctor proxy check (presence, not truthiness).
- Fixed: `?key=` redirect could emit a protocol-relative `Location: //host`; now always a single-slash local path.
- Hardened: `_loads` turns RecursionError from deeply nested JSON into 400; request stall timeout is the `REQ_TIMEOUT` constant (10 s).
- Verified, no change: UDP replies are capped at 1232 bytes with TC set (TCP retry); responses (QR=1) never answered; non-allowed sources get silence; unlock limit is per address and ignores cookies; sessions max 16 and expire server-side; settings/led reject every non-bool/non-string type; no env var is read anywhere and no flag, setting key or endpoint touches the adult guard (grep-checked in a test).
- Residual: a client dripping bytes slower than the 10 s stall timeout can hold an HTTP slot (8 per address, 32 total) as there is no total request deadline; behind `tailscale serve` all callers share 127.0.0.1, so 5 bad unlocks lock everyone out for a minute; plain HTTP exposes the token cookie on the LAN (use Tailscale TLS, section 2); UDP source addresses inside the allow-list can be spoofed by a LAN neighbour (reflection is limited to 1232 bytes per query and the 60 qps limit).
