# Auto-DNS routes for Overheard (R16)

Goal: your own devices use the board (100.69.41.76) for DNS without touching each one by hand.

## What Apple profiles can and cannot do (checked against Apple docs)

- `com.apple.dnsSettings.managed` configures **encrypted DNS only**: Protocol is `HTTPS` or `TLS`.
  <https://support.apple.com/guide/deployment/dep86469ba99/web> and
  <https://developer.apple.com/documentation/devicemanagement/dnssettings>
- `com.apple.wifi.managed` has **no DNS keys** (SSID, auth, proxy, QoS only).
  <https://support.apple.com/guide/deployment/dep168e876c9/web>
- The board serves plain UDP/TCP 53. So **a plain-DNS iPhone profile is not possible**, and
  `tools/make_profile.py` deliberately does not make one by default (it would do nothing or break DNS).
  "Make iPhone Profile.command" writes manual steps to `~/Desktop/ArduinoQ/iPhone-DNS-steps.txt`.

## Lane B: iPhone/iPad, manual (once per Wi-Fi network)

1. Settings > Wi-Fi > (i) next to the network > Configure DNS > Manual.
2. Remove existing servers, add `100.69.41.76`, Save.
3. Turn off iCloud Private Relay and "Limit IP Address Tracking" for that network (see Limits).

## Lane D: Tailscale (best zero-touch; works anywhere, per-device addresses)

1. Install Tailscale on the board and on each of your devices; sign in to the same tailnet.
2. Admin console > DNS > Nameservers > Add nameserver > Custom: the board's tailnet IP
   (`tailscale ip -4` on the board) and turn on **Override local DNS**.
3. Devices now send all DNS to the board whenever Tailscale is on, on Wi-Fi or cellular.
4. Each device reaches the board from its own tailnet address, so the dashboard can tell
   devices apart (no shared-NAT blur like behind a hotel/dorm router).
5. MagicDNS gives names such as `unoq` / `unoq.<tailnet>.ts.net` for the board and each device.
6. Check: `tailscale status` lists devices and their 100.x addresses; on a device run
   `tailscale dns status` (or `nslookup example.com`) and confirm the board answers.

## Lane A: your own router or travel AP

If you control the router (e.g. a travel router), set DHCP option 6 (DNS server) to the
board's LAN address. Every client that joins gets it automatically. Needs the board on that LAN.

## Future: DNS-over-TLS on the board (would unlock a real iPhone profile)

- Get a cert: `tailscale cert <board>.<tailnet>.ts.net` (needs HTTPS enabled in the admin console).
- Serve TLS on port 853 with stdlib `ssl` wrapping the existing DNS-over-TCP handler (2-byte length framing).
- Then `python3 tools/make_profile.py --dot-host <board>.<tailnet>.ts.net` produces a
  `.mobileconfig` (AirDrop, Settings > Profile Downloaded). Do not install it before DoT works: DNS would fail.
- The cert name only resolves/connects over Tailscale, so this is Lane D plus a profile, not a LAN solution.

## Limits

- iCloud Private Relay and Limit IP Address Tracking bypass or hide DNS choices.
- Apps and browsers with their own DNS-over-HTTPS (Firefox, Chrome "secure DNS") skip the board.
- The 3DS cannot join Tailscale and has no profile support: set its DNS by hand in connection settings.
- Tailscale off = DNS reverts to the network's default (nothing is blocked).

## Out of scope

Pushing DNS to the whole building LAN (rogue DHCP server, ARP spoofing) is **not** done: it would
hijack other tenants' traffic without consent. Only your own devices and your own network are covered.
