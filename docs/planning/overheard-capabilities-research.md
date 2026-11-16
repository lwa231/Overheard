# Overheard: furthest realistic capabilities with an own router (research, 2026-11-12)

Scope: the owner's own router, own private subnet, own devices only. Web content treated as untrusted reference. Nothing was run on the board. "UNVERIFIED" = not confirmed from a source I could read. Search budget was about 25 calls, so depth is limited.

## Verdict

With its own router the UNO Q 4 GB is a very good **DNS and policy brain** and a poor **inline gateway**. It has four Cortex-A53 cores, 4 GB RAM, Debian, one Wi-Fi 5 radio and no Ethernet port (wired only via a USB-C dongle/hub). The realistic ceiling is: a recursive, encrypted, per-client DNS resolver with DHCP, schedules, local zones and a dashboard; Tailscale reach and a subnet router for light traffic; and the router doing the enforcement (port-53 redirect, DoT/DoH-resolver blocking, VLAN/guest split) while the board supplies the lists and decisions. Packet-level IDS, flow analytics and routing need either a router that exports logs/flows to the board, or a wired USB adapter, and even then are limited to light home loads. Biggest unknown: real throughput and kernel features (netfilter, WireGuard, Docker) on the board's Debian image; none were found documented.

## Hardware facts

| Item | Fact | Source |
|---|---|---|
| SoC | Qualcomm Dragonwing QRB2210, 4x Cortex-A53 up to 2.0 GHz | [Arduino docs](https://docs.arduino.cc/hardware/uno-q/), [CNX](https://www.cnx-software.com/2025/10/07/qualcomm-acquires-arduino-introduces-arduino-uno-q-dual-brain-sbc/) |
| GPU / DSP | Adreno 702 (OpenGL ES 3.1, Vulkan 1.1, OpenCL 2.0 per CNX); Hexagon DSP v66 (CNX) | [CNX](https://www.cnx-software.com/2025/10/07/qualcomm-acquires-arduino-introduces-arduino-uno-q-dual-brain-sbc/) |
| NPU / TOPS | No TOPS figure found for QRB2210. Arduino marketing mentions an NPU, but no spec backs it; inference is said to run on CPU/GPU. The 40 TOPS NPU belongs to the different VENTUNO Q board. NPU: UNVERIFIED | [Qualcomm](https://www.qualcomm.com/products/internet-of-things/robotics-processors/qrb2210), [Waveshare](https://docs.waveshare.com/Arduino-UNO-Q-02016) |
| Memory | ABX00162: 2 GB RAM / 16 GB eMMC; ABX00173: 4 GB RAM / 32 GB eMMC (LPDDR4 vs LPDDR4X differs between sources) | [CNX](https://www.cnx-software.com/2025/10/07/qualcomm-acquires-arduino-introduces-arduino-uno-q-dual-brain-sbc/), [Waveshare](https://docs.waveshare.com/Arduino-UNO-Q-02016) |
| Companion MCU | STM32U585 Cortex-M33, 160 MHz, 2 MB flash, 786 KB SRAM, runs Arduino core on Zephyr | [Arduino docs](https://docs.arduino.cc/hardware/uno-q/) |
| MPU to MCU link | "Arduino Bridge" RPC library. Physical bus not stated in sources read: UNVERIFIED. The MCU has no USB; it reaches the network only through the Bridge | [Waveshare](https://docs.waveshare.com/Arduino-UNO-Q-02016), [Arduino docs](https://docs.arduino.cc/hardware/uno-q/) |
| Wireless | WCBN3536A module: Wi-Fi 5 dual-band 2.4/5 GHz, Bluetooth 5.1, onboard antennas. One radio | [Arduino docs](https://docs.arduino.cc/hardware/uno-q/) |
| Wi-Fi AP / bridge mode | No source found for hotspot, access point or bridge use. UNVERIFIED | (searched, none) |
| Ethernet | None built in. Wired only through a USB-C dongle/hub; official 8-in-1 hub exists; one user got DHCP via hub Ethernet | [Arduino docs](https://docs.arduino.cc/hardware/uno-q/), [Arduino hub](https://store.arduino.cc/products/usb-c-hub), [forum](https://forum.arduino.cc/t/uno-q-wifi-failed/1431889) |
| USB-C | One port: power, programming, host/device switching, video via dongle. USB speed not stated in sources read: UNVERIFIED. In SBC mode a hub needs its own PD supply and powers the board | [Waveshare](https://docs.waveshare.com/Arduino-UNO-Q-02016), [forum](https://forum.arduino.cc/t/uno-q-usb-port-not-working-if-board-powered-from-5v/1442207) |
| USB host caveat | If powered via VIN instead of USB-C, USB host does not work (dwc3-qcom driver; Arduino says unsupported; workaround exists) | [GitHub fix](https://github.com/Psalmustrack/arduino-uno-q-usb-fix) |
| Power in | USB-C 5 V / 3 A, or VIN 7-24 V | [Qualcomm](https://www.qualcomm.com/developer/hardware/arduino-uno-q) |
| Power draw | One forum post cites 0.5 W idle (Geerling sbc-reviews issue #83, which I could not open). Treat as UNVERIFIED | [forum](https://forum.arduino.cc/t/what-is-the-power-consumption-of-the-arduino-uno-q/1408753) |
| OS | Debian Linux on MPU. Kernel 6.16.7 reported by a user. netfilter/WireGuard/Docker support in that kernel: UNVERIFIED | [forum](https://forum.arduino.cc/t/getting-a-usb-wifi-dongle-working-on-the-uno-q/1456444.md) |
| LED matrix | 8x13, on the STM32 side. Most sources: blue, 3-bit grayscale (Waveshare); CNX says RGB (conflict, UNVERIFIED). Plus 4 RGB LEDs (2 user, 2 system), user and power buttons | [Waveshare HW](https://docs.waveshare.com/Arduino-UNO-Q-02016/Hardware-Interfaces), [CNX](https://www.cnx-software.com/2025/10/07/qualcomm-acquires-arduino-introduces-arduino-uno-q-dual-brain-sbc/) |
| GPIO | 3.3 V logic; most pins 5 V tolerant except A0/A1. UNO header, Qwiic, high-speed carrier connectors | [Waveshare](https://docs.waveshare.com/Arduino-UNO-Q-02016) |
| Proven workloads | Pi-hole as a custom App Lab container (4 GB model); Arduino blog also names Home Assistant, n8n, Frigate | [Project Hub](https://projecthub.arduino.cc/AndreaRichetta/protect-your-home-from-adv-using-uno-q-and-pi-hole-e4b834), [Wevolver](https://www.wevolver.com/article/from-home-assistant-to-ai-agents-what-linux-unlocks-on-the-arduino-uno-q-board) |

Note: the official datasheet PDF ([ABX00162-ABX00173](https://docs.arduino.cc/resources/datasheets/ABX00162-ABX00173-datasheet.pdf)) was fetched but unreadable by my tools (image-based). The table relies on the doc pages, CNX and Waveshare.

## What the own router changes

- Router DHCP hands out the board as DNS (option 6). Option 6 is advisory only: hard-coded resolvers ignore it ([sources](https://devbytes.co.in/news/how-dhcp-option-6-can-break-your-dns-filtering-solution)). Changes apply as leases renew.
- Enforcement belongs on the router: redirect or block outbound port 53, block known DoT (853) and public DoH resolver IPs, disable IPv6 DNS leaks. The board cannot do this unless it is inline. Needs a router with firewall rules (OpenWrt-class or similar).
- A separate subnet or VLAN/guest network means the board only ever sees the owner's own devices. Needs a router or AP with VLAN or guest-SSID support.
- The board stays a Wi-Fi client or gets a USB Ethernet link; the router does routing. This avoids the board's biggest limit (single radio, USB adapter).

## Capability table

Effort: S small, M medium, L large. "Fits" = plausible on 4x A53 / 4 GB / Wi-Fi 5 or USB-Ethernet.

| Capability | What it gives | Needs | Effort | Fits this board? | Main risk | Source |
|---|---|---|---|---|---|---|
| Blocklist DNS (current Overheard) | Ads/trackers/malware blocked per query | Router DHCP option 6 | done | Yes. Pi-hole runs on this board | Bypass by DoH/hard-coded DNS | [Project Hub](https://projecthub.arduino.cc/AndreaRichetta/protect-your-home-from-adv-using-uno-q-and-pi-hole-e4b834) |
| Local recursive resolver (Unbound-style) | No third-party upstream sees queries; DNSSEC validation | Package that builds on arm64 Debian | S-M | Yes; Pi Zero 2 W (weaker) is reported fine, unverified claims | Cold-cache latency; ISP blocks on port 53 | [DietPi forum](https://dietpi.com/forum/t/pi-hole-unbound-on-raspberry-pi-zero-2w/25084) |
| Serve DoT/DoH/DoQ to own devices | Encrypted DNS from phone/Mac outside home and in | TLS cert (Tailscale or own CA); resolver supporting it | M | Yes. Technitium and AdGuard Home list DoT/DoH (Technitium also DoQ); Overheard (stdlib Python) would need a TLS front | Cert renewal; QUIC UDP load UNVERIFIED | [Technitium](https://technitium.com/dns/), [AdGuard Home](https://github.com/AdguardTeam/AdGuardHome) |
| Split-horizon / local zones | `nas.home` names, per-network answers | Resolver feature | S | Yes | Name collisions | [Technitium](https://technitium.com/dns/) |
| Per-client policies + schedules | Kids/guest profiles, bedtime rules, time-based blocking | Stable client identity (static DHCP leases or MAC reservations); AdGuard/Technitium per-client lists exist; schedules would be Overheard logic | S-M | Yes | Identity is by IP/MAC; randomized MACs on phones break it | [Technitium](https://technitium.com/dns/) |
| DHCP server on the board | Full visibility of hostnames and leases, no router dependency | Router DHCP disabled; board must stay up | M | Yes (Technitium, AdGuard Home have DHCP) | Board outage = network outage | [AdGuard Home](https://github.com/AdguardTeam/AdGuardHome) |
| Router lease/hostname feed | Names for every client without being DHCP | Router that exports leases (API/syslog) | S-M | Yes (tiny load) | Router-specific; UNVERIFIED per model | general practice |
| Tailscale on board + MagicDNS/split DNS | Overheard DNS for phone/Mac away from home | Tailscale (already planned) | S | Yes, pattern documented on Pi | Tailscale on this kernel: UNVERIFIED | [Tailscale Pi-hole guide](https://tailscale.com/kb/1114/pi-hole) |
| Tailscale subnet router | Reach the private subnet remotely | IP forwarding, advertise routes, approve | S | Yes for light traffic; throughput UNVERIFIED | Wi-Fi single radio shares RX/TX | [Tailscale](https://tailscale.com/kb/1019/subnets) |
| Tailscale exit node | All phone traffic through home | Same plus exit-node approval | S | Light use only; throughput UNVERIFIED | Wi-Fi 5 + A53 ceiling; do not combine SNAT-off with exit node | [Tailscale](https://tailscale.com/kb/1019/subnets) |
| WireGuard (plain) | Simple VPN | Kernel WireGuard module (UNVERIFIED) or userspace | M | Probably; UNVERIFIED | Module availability | none read |
| DNS-driven nftables sets | Block or allow by IP learned from DNS answers; kill-switch lists | nftables + kernel modules; board inline OR router cooperation | M-L | Only if kernel has netfilter (UNVERIFIED); needs inline path | dnsmasq race (reply before set update), cached lookups skip sets | [OpenWrt docs](https://openwrt.org/docs/guide-user/firewall/filtering_traffic_at_ip_addresses_by_dns) |
| Force DNS via router | Redirect port 53, block 853/DoH resolver IPs | Router firewall rules | S-M | Router does the work; board only answers | IPv6 leaks, DNAT without SNAT quirks | [labzilla](https://labzilla.io/blog/force-dns-pihole), [Pi-hole forum](https://discourse.pi-hole.net/t/pi-hole-not-receiving-dns-queries-despite-correct-dhcp-dns-direct-queries-work-suspected-router-dns-interception/85254) |
| Private Relay / Firefox DoH signals | Answer `mask.icloud.com`, `mask-h2.icloud.com` negatively (Apple documents this); `use-application-dns.net` NXDOMAIN (Mozilla canary) | DNS rule only | S | Yes | Mozilla canary only stops auto-enable; manual DoH ignored | [Apple](https://developer.apple.com/support/prepare-your-network-for-icloud-private-relay/), [Mozilla](https://support.mozilla.org/en-US/kb/canary-domain-use-application-dnsnet) |
| VLAN / guest isolation | Owner-only devices on one subnet, IoT on another, board per-VLAN DNS | VLAN-capable router/AP or managed switch | M | Board needs a tagged interface (USB-Ethernet) or one DNS IP reachable from each VLAN | Misrouted firewall rules | [AdGuard](https://github.com/AdguardTeam/AdGuardHome) (general) |
| NetFlow/ntopng-style flows | Bytes per device, top talkers, new-destination alerts | Router exporting flows/conntrack, or board inline, or a mirror port | L | Receiver side plausible; heavy capture no. ntopng is write-heavy (SSD advice); Pi RAM minimums UNVERIFIED | eMMC wear, CPU | [ntop mirror guide](https://www.ntop.org/guides/ntopng/use_cases/mirror_tap_monitoring.html) |
| Suricata / Zeek IDS | Signature or protocol-level detection | Traffic copy (SPAN or inline) + second NIC (USB adapter); own network only | L | Marginal: vendor-claimed ~150 Mbps on a Pi 5 4 GB (unreliable, vendor-sold rival). Rules inflate RAM; 4 GB is a minimum, not margin | Memory, drops, USB NIC limits | [HookProbe](https://dev.to/hookprobe/suricata-vs-zeek-vs-napse-best-edge-ids-for-small-business-1b5k), [Netgate](https://forum.netgate.com/post/113047) |
| CrowdSec | Shared threat feeds against exposed services | Services exposed to internet (not applicable to DNS-only box) | M | Likely; no source found: UNVERIFIED | Low value without exposed services | none |
| mDNS / device fingerprinting | Device names, types, "new device joined" alerts | Same L2 segment; passive listen on own LAN | M | Yes (tiny load) | Privacy norms; own devices only | general practice |
| Threat-intel feeds | Auto-updated blocklists, new-domain/DGA heuristics | Outbound HTTPS | S | Yes | Feed quality and false positives | [Technitium](https://technitium.com/dns/) |
| Honeypot / canary tokens | Alert if an internal host resolves a canary name or probes a decoy IP | Decoy DNS names, optional decoy listener | S-M | Yes | Alert fatigue | general practice |
| Captive portal | Guest sign-in | Be the gateway or have router redirect | L | Poor (needs inline) | Complexity, HTTPS interception limits | none |
| Local ML anomaly detection | Flag odd DNS patterns (volume, entropy, rare domains) | Query log history | M | Yes for tiny models on CPU; no verified accelerator numbers | Few labeled data, false positives | [Qualcomm](https://www.qualcomm.com/products/internet-of-things/robotics-processors/qrb2210) |
| Home Assistant integration | Presence from DHCP/Tailscale, automations on alerts | HA on board or the Ubuntu server | M | Arduino lists HA as possible; heavy alongside DNS on 4 GB: UNVERIFIED | RAM contention | [Wevolver](https://www.wevolver.com/article/from-home-assistant-to-ai-agents-what-linux-unlocks-on-the-arduino-uno-q-board) |
| MCU physical alerts | LED matrix status (queries/sec, blocks, alert glyph), RGB LED, buzzer on GPIO, button to pause blocking, small display via I2C/SPI | Bridge calls from Overheard to sketch | S-M | Yes, this is the board's unique strength | Bridge API stability (new platform) | [Waveshare](https://docs.waveshare.com/Arduino-UNO-Q-02016/Hardware-Interfaces), [Wevolver](https://www.wevolver.com/article/from-home-assistant-to-ai-agents-what-linux-unlocks-on-the-arduino-uno-q-board) |
| Frigate / cameras | Local camera detection | USB or RTSP cameras | L | Arduino names it; competing with DNS for CPU | CPU saturation | [Wevolver](https://www.wevolver.com/article/from-home-assistant-to-ai-agents-what-linux-unlocks-on-the-arduino-uno-q-board) |

## Top 8 to build next, in order

1. **Router-side enforcement pack** (DHCP option 6, redirect port 53, block 853 and public DoH IPs, IPv6 DNS leak check, Private Relay and Firefox canary answers). Biggest jump in coverage for the least board load.
2. **Per-client profiles + schedules** keyed on static leases (MAC reservations on the own router). Delivers parental/time rules on top of existing DNS.
3. **MCU status layer** (LED matrix gauge, pause button, buzzer alert). Cheap, unique to this hardware, tests the Bridge early.
4. **Tailscale split DNS + subnet router** so phone and Mac use Overheard everywhere and reach the private subnet. Confirms kernel support before anything harder.
5. **Local recursive resolver with DNSSEC** (no third-party upstream). Privacy win; fits 4 GB easily.
6. **Router lease/hostname feed + new-device alerts + mDNS names**. Better dashboard names, "unknown device joined" alert, still DNS-light.
7. **Encrypted DNS serving (DoH/DoT) for away-from-home devices**, via a TLS front or by adopting Technitium/AdGuard Home for that role.
8. **DNS anomaly scoring** (rare domains, entropy, query bursts, canary names) with a small local model or rules. Honest "alerts for the owner", not enforcement.

Defer: flow analytics (needs router export), Suricata/Zeek (needs mirror or inline plus second NIC), inline DNS-driven nftables, captive portal.

## Cannot do / should not do

Cannot do with DNS-level control alone:
- Stop apps that use their own encrypted DNS (DoH/DoT built into browsers or apps) or that hard-code resolver IPs. Only router firewall rules reduce this, and DoH to a major CDN IP is hard to block cleanly.
- See or block traffic to hard-coded IP addresses (no DNS lookup happens).
- Inspect QUIC/HTTP3 content; DNS only sees the name, never the page, path or payload.
- Break iCloud Private Relay for a user who has it on. The documented route is to answer the two Apple hostnames negatively so the device warns the user; the user can still choose to stay on Private Relay on another network ([Apple](https://developer.apple.com/support/prepare-your-network-for-icloud-private-relay/)).
- Guarantee Firefox DoH is off: the canary domain only affects automatic enablement ([Mozilla](https://support.mozilla.org/en-US/kb/canary-domain-use-application-dnsnet)).
- Control IPv6 clients that get a resolver from router advertisements unless the router is configured for it.
- See per-device traffic volume, throttle bandwidth or isolate devices: needs inline routing, flow export or a mirror port, not a passive DNS box.
- Run inline gateway duty at line rate on one Wi-Fi 5 radio or a USB Ethernet adapter. Throughput is UNVERIFIED and likely well below gigabit.
- Use an NPU: none confirmed on QRB2210.

Should not do (legal and ethical):
- Do not monitor, intercept, redirect, spoof (ARP/DHCP/DNS), probe or log devices that are not the owner's own, or any shared or building network. A private subnet behind the owner's own router is the line.
- Do not decrypt (TLS-intercept) other people's traffic, including guests' or housemates'. If guests join, disclose logging and keep the guest network separate.
- Do not use identifying query logs of other people without their knowledge; set short retention and tell household members.
- Do not run honeypots that reach out or attack; keep them passive and internal.
- Do not rely on adult-content or safety filters as a security boundary (the owner's spec: filters hard-coded; slowdown separate toggle).
- Keep to the project rule: no demo mode, and label anything not hardware-tested.

## Sources

Hardware and platform
- Arduino UNO Q docs: https://docs.arduino.cc/hardware/uno-q/
- Arduino datasheet (unreadable by tools): https://docs.arduino.cc/resources/datasheets/ABX00162-ABX00173-datasheet.pdf
- CNX Software launch article: https://www.cnx-software.com/2025/10/07/qualcomm-acquires-arduino-introduces-arduino-uno-q-dual-brain-sbc/
- Waveshare UNO Q wiki: https://docs.waveshare.com/Arduino-UNO-Q-02016 and /Hardware-Interfaces
- Qualcomm UNO Q page: https://www.qualcomm.com/developer/hardware/arduino-uno-q
- Qualcomm QRB2210: https://www.qualcomm.com/products/internet-of-things/robotics-processors/qrb2210
- Arduino USB-C hub: https://store.arduino.cc/products/usb-c-hub
- USB host/VIN fix: https://github.com/Psalmustrack/arduino-uno-q-usb-fix
- Forum: power https://forum.arduino.cc/t/what-is-the-power-consumption-of-the-arduino-uno-q/1408753 ; USB https://forum.arduino.cc/t/uno-q-usb-port-not-working-if-board-powered-from-5v/1442207 ; Wi-Fi/Ethernet https://forum.arduino.cc/t/uno-q-wifi-failed/1431889 ; dongle https://forum.arduino.cc/t/getting-a-usb-wifi-dongle-working-on-the-uno-q/1456444.md
- Pi-hole on UNO Q: https://projecthub.arduino.cc/AndreaRichetta/protect-your-home-from-adv-using-uno-q-and-pi-hole-e4b834
- Wevolver UNO Q + Linux services: https://www.wevolver.com/article/from-home-assistant-to-ai-agents-what-linux-unlocks-on-the-arduino-uno-q-board

Software and network
- Technitium DNS: https://technitium.com/dns/
- AdGuard Home: https://github.com/AdguardTeam/AdGuardHome
- Tailscale subnet routers and exit nodes: https://tailscale.com/kb/1019/subnets ; Pi-hole + Tailscale: https://tailscale.com/kb/1114/pi-hole
- Apple Private Relay network guidance: https://developer.apple.com/support/prepare-your-network-for-icloud-private-relay/ and https://support.apple.com/en-us/102602
- Mozilla canary domain: https://support.mozilla.org/en-US/kb/canary-domain-use-application-dnsnet
- Forcing DNS through Pi-hole: https://labzilla.io/blog/force-dns-pihole ; https://devbytes.co.in/news/how-dhcp-option-6-can-break-your-dns-filtering-solution ; https://discourse.pi-hole.net/t/pi-hole-not-receiving-dns-queries-despite-correct-dhcp-dns-direct-queries-work-suspected-router-dns-interception/85254
- Pi Zero 2 W Pi-hole + Unbound: https://dietpi.com/forum/t/pi-hole-unbound-on-raspberry-pi-zero-2w/25084
- dnsmasq/nftables sets: https://openwrt.org/docs/guide-user/firewall/filtering_traffic_at_ip_addresses_by_dns
- ntopng mirror/TAP: https://www.ntop.org/guides/ntopng/use_cases/mirror_tap_monitoring.html
- Suricata on small hardware (weak sources): https://dev.to/hookprobe/suricata-vs-zeek-vs-napse-best-edge-ids-for-small-business-1b5k ; https://forum.netgate.com/post/113047

## Still UNVERIFIED (test on the board before promising)

USB-C speed and host reliability; real Wi-Fi and USB-Ethernet throughput; idle and loaded power; Wi-Fi AP/bridge mode; kernel netfilter, WireGuard, Docker support on the shipped Debian image; physical MCU-MPU bus; NPU/DSP usable for inference; LED matrix colour (blue vs RGB); Tailscale throughput on A53; CrowdSec fit; Home Assistant plus DNS co-residency on 4 GB; Suricata/Zeek numbers on this SoC.
