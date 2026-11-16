# Apartment subnet: your own router, two boards (R19)

Status: **everything here is UNTESTED on the real hardware until you run it.** Doc links sit next to each claim; "UNVERIFIED" marks what I could not check.
No real addresses are in this repo. `10.10.50.x` is the plan, `100.64.0.x` stands for a Tailscale address, `<...>` is yours to fill in.
The router is "the router": the plan was a Netgear WNR2000, but you may buy a newer gigabit one. Steps a to c are written for any router; the WNR2000 specifics are in one labelled note at the end of step a.

## The plan in one picture

```
building wall jack (DHCP, 100.69.x.x) -> router WAN
router 10.10.50.1  (DHCP .50-.200, Wi-Fi)
  board (UNO Q)  10.10.50.2   static on the board; DNS + monitoring only, nothing routes through it
  server         10.10.50.10  wired, static, Tailscale subnet router for 10.10.50.0/24
  desktop PC     10.10.50.11
  clients        10.10.50.50-.200
```
Default gateway stays the router. DNS at the apartment is the board only (no second resolver for clients): fast, strict, and it needs the recovery card in step g.

## a. At the house, today: the router (any model)

Settings to make, in any router's admin pages (menu names differ: look for the words in quotes):

1. Admin password: set a long one first. Remote management / "WAN access to the admin page": **off**. WPS: **off**. UPnP: off unless you need it.
2. Internet / WAN: "Dynamic IP / DHCP", no login. If the building registers MAC addresses you may need "MAC clone" with the registered MAC (ask them).
3. LAN: router IP **10.10.50.1**, mask **255.255.255.0**, DHCP server **on**, pool **10.10.50.50 to 10.10.50.200**. Save: the router restarts and your PC needs a new lease (unplug/replug).
4. Wi-Fi: a name, **WPA2-PSK with AES** (or WPA3 if the router has it; never WEP/TKIP/open), a long passphrase.
5. Address reservations ("DHCP reservation", "static lease"): PC's MAC -> **10.10.50.11**, board's Wi-Fi MAC -> **10.10.50.2**. They are only used **while the router is the DHCP server (Outcome A in step b)**. In Outcome B the router's DHCP is off and the same two reservations live in the dnsmasq config instead (step c). The server (.10) and the board (.2) are static in their own settings either way.
6. Firmware: update it if the maker still ships updates. Note the version.

**WNR2000 note (UNVERIFIED menu names, from memory of the stock firmware: read the page titles).** The hardware version is on the sticker on the bottom (`v1` to `v5`; the firmware page differs per version). Login `http://routerlogin.net`, `admin` / `password` on a factory unit. Pages: Basic Settings (Internet and the DNS field), Advanced > Setup > LAN Setup (IP, DHCP pool, Address Reservation), Wireless Settings (WPA2-PSK [AES]; WPS under Advanced Setup), Advanced > Advanced Setup > Remote Management, Maintenance > Set Password. Manual: <https://www.manualowl.com/m/Netgear/WNR2000/Manual/3979>. The WNR2000 is **end of life**: Netgear generally ships no new fixes for EOL models (a user reply on the Netgear community says so, it is not an official notice: <https://community.netgear.com/discussions/home-wifi-routers-general/warning-vulnerability-id-non-2015-0211-on-my-netgear-router-wnr2000v3-please-hel/996516/replies/1030264>). Keep remote management off and the passphrase long, and plan to replace it: a newer gigabit router removes the 100 Mbps wired and 2.4 GHz-only limits in step h.

## b. The 5-minute DHCP/DNS test (decides step c)

Question: can the router hand out **10.10.50.2** as the clients' DNS server, or only itself?

1. Router, the DNS field of the internet/WAN page ("Use these DNS servers", "DNS server", or "DHCP option 6" on the LAN page): Primary **10.10.50.2**, Secondary **empty**, apply. (On the WNR2000 the manual says DHCP clients get the router's own address unless a primary DNS is entered on Basic Settings: UNVERIFIED on your unit, which is why we test.)
2. Make one client renew: disconnect/reconnect Wi-Fi.
3. Read what it was given:
   - Windows: `ipconfig /all` > "DNS Servers".
   - Mac: `scutil --dns | grep nameserver` (first resolver block).
   - iPhone: Settings > Wi-Fi > (i); the DNS line may not be shown on all iOS versions (UNVERIFIED): use the dashboard instead. Make sure "Configure DNS" is **Automatic**.
4. Dashboard check (the real answer): browse a few sites on two devices, then open the Overheard dashboard. Distinct client addresses (10.10.50.50-.200) = clients ask the board directly. **Everything from 10.10.50.1** = the router intercepts and forwards.

Outcome A: clients show 10.10.50.2 as DNS and distinct addresses: **the router keeps DHCP**. Done with this step.
Outcome B: clients get 10.10.50.1, or the dashboard shows only 10.10.50.1: DHCP moves to the server (step c). Do not live with it: you lose the per-device view, and the board's limit of 60 queries/s per client would apply to the whole apartment at once.

## c. Outcome B: dnsmasq on the server, DHCP only

dnsmasq options checked against <https://thekelleys.org.uk/dnsmasq/docs/dnsmasq-man.html> (`port=0` turns DNS off; `dhcp-range` takes a lease time last; `dhcp-authoritative` for the only DHCP server; `interface` plus `bind-interfaces` listen only on the named interface). Option 6 is the DNS-server option, so it is written numerically.

On the server (you run sudo; the server is `awl@awlserver`). First give the server its static address (netplan; interface name from `ip -br link`; the shape is standard netplan, **UNVERIFIED on Ubuntu 26.04**):
```
sudo tee /etc/netplan/60-apartment.yaml <<'EOF'
network:
  version: 2
  ethernets:
    <wired-nic>:
      dhcp4: false
      addresses: [10.10.50.10/24]
      routes:
        - to: default
          via: 10.10.50.1
      nameservers:
        addresses: [10.10.50.2]
EOF
sudo chmod 600 /etc/netplan/60-apartment.yaml && sudo netplan try
```
(`netplan try` rolls back by itself if you do not confirm.) Then dnsmasq. `apt` **starts it at install time with its default config**, so write the config and then **restart** it (and enable it for boot):
```
sudo apt install dnsmasq
sudo tee /etc/dnsmasq.d/overheard-dhcp.conf <<'EOF'
# DHCP only, on the wired LAN interface only. port=0 switches dnsmasq's DNS off: Overheard on the board is the only resolver.
port=0
interface=<wired-nic>
bind-interfaces
dhcp-authoritative
dhcp-range=10.10.50.50,10.10.50.200,255.255.255.0,24h
dhcp-option=option:router,10.10.50.1
dhcp-option=6,10.10.50.2
# reservations: these replace the router's reservation table (the router's DHCP is off in this outcome)
dhcp-host=<desktop-pc-mac>,10.10.50.11,desktop
dhcp-host=<board-wifi-mac>,10.10.50.2,board
EOF
sudo dnsmasq --test
```
Order matters (two DHCP servers on one LAN is how outages start): **router: untick "Use Router as DHCP Server" / turn DHCP off and save**, then `sudo systemctl enable dnsmasq && sudo systemctl restart dnsmasq`, then reconnect one client. Check it listens for DHCP only, on the LAN only: `sudo ss -lunp | grep dnsmasq` must show port 67 on the wired interface's address and **no port 53** (the board's reservation only matters if the board ever falls back to DHCP, e.g. after the 90 s revert: it then still gets .2). If `ufw` is on: `sudo ufw allow in on <wired-nic> to any port 67 proto udp`. Watch: `sudo journalctl -u dnsmasq -f`.
Cost to know: with the server off, **new devices get no address** (existing 24 h leases keep working). That is the price of Outcome B.

## d. The server as Tailscale subnet router

Purpose: reach 10.10.50.x (router page, PC, server) from away. Not needed for DNS. Commands from <https://tailscale.com/kb/1019/subnets>:
```
echo 'net.ipv4.ip_forward = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf
echo 'net.ipv6.conf.all.forwarding = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf
sudo sysctl -p /etc/sysctl.d/99-tailscale.conf
sudo tailscale set --advertise-routes=10.10.50.0/24
```
(IPv6 forwarding stops a SLAAC host accepting router advertisements: on the wired server with a static IPv4 plan this is harmless, but if it also uses IPv6 from the router, add `net.ipv6.conf.<wired-nic>.accept_ra = 2` first; kernel behaviour, not re-read this session.)
Then approve: admin console > Machines > the server > Subnets > tick 10.10.50.0/24 > Save. A **Linux** client that should use it: `sudo tailscale set --accept-routes` (Linux does not by default; Windows, iOS, Android and both macOS variants **do**: <https://tailscale.com/kb/1080/cli>).
Caveat: a device that is **physically on 10.10.50.0/24 should not also take that route from Tailscale**. The Tailscale docs have no warning for this case (checked), so the mechanism is **UNVERIFIED**; my reasoning is that the tailnet route could win over the local one and hairpin LAN traffic through the server. On the PC and Mac at the apartment: `tailscale set --accept-routes=false`. On the iPhone there is no such switch that I could verify: if the phone is slow at home, that is the first suspect. Never use 10.10.50.0/24 for the home site.
Do not turn off SNAT (`--snat-subnet-routes=false`): you would then need a return route for 100.64.0.0/10 pointing at the server on every LAN device or on the router (same doc). Leave the default.

## e. The board

1. Tailscale must stay on and not take over the board's DNS (the tailnet nameserver will point at the board itself): `sudo tailscale set --accept-dns=false` (flag exists: <https://tailscale.com/kb/1080/cli>; the reason is my inference, **UNVERIFIED**).
2. Add two lines to **`sites/apartment.conf`** (your file; I did not touch it):
   ```
   BOARD_LAN_IP=10.10.50.2/24
   BOARD_LAN_GW=10.10.50.1
   ```
3. **Change `BOARD_HOST`** in `board.conf` and `sites/apartment.conf`. Today it is the **building** address (a 100.69.x.x one); after the move it stops working. On the board run `tailscale ip -4` and put that answer there:
   ```
   BOARD_HOST=100.64.0.x
   ```
   (`BOARD_MDNS` can stay.) Check it from the Mac first: `bash scripts/status.sh`.
4. **Join the board to the router's Wi-Fi, with a way back.** Switching Wi-Fi networks over SSH drops your session and can strand the board. Do it with a safety net:
   - Best: do it while you can still reach the board another way (USB-C to the Mac / App Lab, or a keyboard and screen; UNVERIFIED which of these an UNO Q offers: check before you need it).
   - Otherwise use a timed revert. On the board (over Tailscale, sudo password once; `<new-ssid>` is the router's Wi-Fi):
     ```
     OLD="$(nmcli -g GENERAL.CONNECTION device show wlan0)"      # the Wi-Fi it is on now (check the device name with: nmcli device)
     sudo systemd-run --unit=wifi-revert --on-active=180 nmcli connection up "$OLD"
     sudo nmcli device wifi connect "<new-ssid>" --ask
     ```
     From the Mac within 3 minutes: `bash scripts/status.sh`. Healthy? Cancel the revert on the board: `sudo systemctl stop wifi-revert.timer`. Not healthy: do nothing, after 3 minutes the board goes back to the old Wi-Fi by itself.
   - If it does not come back at all: wait 5 minutes (Tailscale needs a moment to reconnect after a network change, UNVERIFIED how long), then power-cycle it. If it joined the wrong network, reach it by the old Wi-Fi or the other route above and run `nmcli connection delete "<new-ssid>"` so it falls back to the saved old one. A wrong passphrase is the usual cause.
5. Then double-click **`Set Board Address.command`** (or `bash scripts/net_static.sh --dry-run` first). It checks Tailscale and systemd-run, asks for the board's sudo password once, sets 10.10.50.2 with NetworkManager, and **puts the board back on DHCP by itself unless a brand-new SSH connection from the Mac finds it healthy** (new address, gateway pings, a name resolves, Tailscale running) within 80 s of the timer being armed. It stops with a message if the board is not on NetworkManager (**UNVERIFIED on a real UNO Q**: which network manager it uses). Undo any time: `bash scripts/net_static.sh --revert`.
   The board's **own** DNS becomes `127.0.0.1` (Overheard) then `9.9.9.9` (plain UDP): the fallback is **only for the board's own lookups** (time sync, updates, Tailscale's control server) so it can still resolve when Overheard is down. Clients are never given 9.9.9.9: they get the board only.
6. Re-run `bash scripts/install.sh`: with `BOARD_LAN_IP` set, the service logs the board's addresses at start and waits up to 30 s for 10.10.50.2 (Wi-Fi comes up late), then starts anyway. An invalid `BOARD_LAN_IP` is reported and the flag is left out (a bad flag could otherwise crash-loop the service); the program itself also ignores a bad `--expect-ip`. The unit has `Restart=always`, `RestartSec=2`, `StartLimitIntervalSec=0`, so a crash loop never leaves DNS permanently stopped.
7. Encrypted upstream: if Cloudflare DoT fails the board tries Quad9 DoT (`--upstream2 9.9.9.9 --tls-name2 dns.quad9.net`) before any plain UDP; if port 853 is filtered, or a provider accepts the connection but never answers, it goes straight to plain UDP (waiting twice would only slow every lookup). The second provider is on by default only while `--upstream` is the built-in default; with your own `--upstream` you must pass `--upstream2` to get one. `--strict` still means never plain.

## f. iPhone and other clients

- **Never hard-code the board's LAN address as DNS on a device.** At the apartment, devices get it from DHCP. Away, they get it from the Tailscale global nameserver (Lane D in `docs/auto-dns.md`). A hard-coded address is what locked the iPhone out before: the old building address does not exist on other networks.
- iPhone: Settings > Wi-Fi > (i) > Configure DNS > **Automatic** (remove the old manual entry).
- Admin console > DNS > Global nameserver: the **board's Tailscale address**, **Override DNS servers on**. Docs: <https://tailscale.com/kb/1054/dns> (override makes devices ignore local DNS; the page describes **no fallback** if the nameserver is unreachable).
- Also tick **"Use with exit node"** on that nameserver: the docs say a device using an exit node uses the exit node as its resolver for all domains unless that is set, which is the likely cause of "DNS not going through the board" while the Boston exit node is on.

## g. Recovery card (DNS is down)

1. From any device with Tailscale (needs no DNS, you type the number): `ssh arduino@100.64.0.x` (the board's Tailscale address), then `sudo systemctl restart overheard` and `systemctl status overheard`; log: `journalctl -u overheard -n 30`. From the Mac: `bash scripts/status.sh`.
2. One device, right now: Mac `sudo networksetup -setdnsservers Wi-Fi 9.9.9.9` (undo `... empty`); iPhone Wi-Fi > (i) > Configure DNS > Manual > 9.9.9.9; Windows PowerShell `Set-DnsClientServerAddress -InterfaceAlias "Wi-Fi" -ServerAddresses 9.9.9.9` (undo `-ResetServerAddresses`). Plain DNS to the building: temporary only.
3. Board off the LAN (no 10.10.50.2)? The 90 s timer or `--revert` puts it on DHCP; it stays reachable over Tailscale either way. The board's own lookups fall back to 9.9.9.9 when Overheard is stopped (board only, never clients), and the existing Tailscale tunnel keeps running; restarting the service fixes the clients.
4. Last resort: unplug the board's power for 10 s. It boots into the service.

## h. Known limits, plainly

- Everything above is **untested on the real hardware**. The scripts were exercised against fake `ssh` only.
- If you use the WNR2000: LAN ports are **10/100** (wired speed tops out near 100 Mbps), Wi-Fi is **2.4 GHz N only**, and the router is **end of life**. A newer gigabit router removes the first two.
- Many buildings tie the wall jack to a registered device or forbid personal routers: **check the lease and building rules first.** Your WAN stays a building 100.69.x.x address behind their NAT: no port forwarding, double NAT.
- **100.64.0.0/10 conflict (UNVERIFIED in detail).** Tailscale devices use 100.64.0.0/10 and the building hands out 100.69.x.x inside it. Tailscale's own page says such conflicts "can arise" when an ISP uses that range, and documents only one fix (turn off IPv4 for the tailnet with the `disable-ipv4` node attribute): <https://tailscale.com/docs/reference/troubleshooting/network-configuration/cgnat-conflicts>. It does **not** describe a device whose own LAN or WAN address sits inside the range, and gives no symptoms. Behind the router every one of your devices is 10.10.50.x (the 100.69 address lives on the router's WAN side only, which does not run Tailscale), so the overlap should stop mattering; today's board is the one device that holds a 100.69 address, and that is why its LAN address cannot be trusted next to Tailscale. Third-party reports of dropped traffic exist (not official). The same page set says the range does not clash with 10.0.0.0/8 or 192.168.0.0/16 (<https://tailscale.com/kb/1015/100.x-addresses>).
- The server is a single point for DHCP in Outcome B, and the board the single DNS server. That is your strict-filtering choice; step g is the safety net.

## i. The home site (second board)

1. Second UNO Q: install as the first (`Install Overheard.command`, `Install Tailscale on Board.command`), join the **home** Wi-Fi.
2. `cp sites/home.conf.example sites/home.conf`; set `BOARD_HOST` to its Tailscale address. Optional keys, only if you want a fixed home address: `BOARD_LAN_IP=<home-lan-address>/24`, `BOARD_LAN_GW=<home-router>`.
3. Home router: <router brand and model: unknown, to fill in>. Home LAN range: <unknown, must NOT be 10.10.50.0/24>. In the router's DHCP settings put the board's home address as the DNS server (name varies: "DNS server", "DHCP option 6"); if the router cannot, the same test and Outcome B as in b/c apply, with the home range.
4. Check: `SITE=home bash scripts/status.sh`. Linking the two dashboards is `Link Sites.command` / `docs/multi-site.md` (writing is not atomic: the result file says which boards were written).

## j. The exit node (Boston VPS), diagnose before you change

`Check VPS.command` (copy `vps.conf.example` to `vps.conf` first) asks the VPS read-only questions over SSH and writes `last-vps-check.txt` with public IPs, logins and the tailnet name hidden: IP forwarding, exit routes advertised and approved, ufw forward policy, Tailscale's own NAT rule, Docker vs ufw, UDP GRO, MTU (reported, never "fixed" blindly), relay vs direct, pending reboot, plus on the Mac: exit node selected, the nameserver addresses from `tailscale dns status`, allow-LAN-access. It prints the exact fix for each failure and changes nothing; fixes that can interrupt a session say so, and none touches sshd or removes a firewall rule. Facts used: exit-node setup <https://tailscale.com/kb/1103/exit-nodes>, UDP GRO forwarding (Tailscale 1.54+, Linux 6.2+) <https://tailscale.com/kb/1320/performance-best-practices>, `netcheck` and `dns status` (1.74+) <https://tailscale.com/kb/1080/cli>.
UNVERIFIED: the "advertised" check uses `tailscale debug prefs`, the Mac check uses its `ExitNodeAllowLANAccess` field, and the NAT check looks for the chain name `ts-postrouting`: none of these is in the public docs; the script says `?` or reports "not found" if they do not answer as expected.
