#!/usr/bin/env bash
# READ-ONLY health check of the Tailscale exit-node VPS. Run from the Mac:  bash scripts/vps_check.sh
# Reads vps.conf (copy vps.conf.example; git-ignored). Changes NOTHING on the VPS: it only runs status commands over SSH and
# prints, for every check, a plain verdict and (when something is wrong) the exact fix command for you to run yourself.
# Public IP addresses are replaced by [public-ip] in everything printed and saved. Saved to ~/Desktop/ArduinoQ/last-vps-check.txt.
# Commands that need root use `sudo -n` (never a password prompt); if that is not allowed the check says "?" instead of guessing.
# UNTESTED against the real VPS. Doc links: subnets/exit nodes https://tailscale.com/kb/1019/subnets and https://tailscale.com/kb/1103/exit-nodes,
# UDP GRO https://tailscale.com/kb/1320/performance-best-practices, DNS https://tailscale.com/kb/1054/dns
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONF="${VPS_CONF:-$ROOT/vps.conf}"
[ -f "$CONF" ] || { echo "Copy vps.conf.example to vps.conf and fill in VPS_USER and VPS_HOST (it is git-ignored)."; exit 1; }
# shellcheck disable=SC1091
. "$CONF"
{ [ -n "${VPS_HOST:-}" ] && [ "${VPS_HOST}" != CHANGE-ME ] && [ -n "${VPS_USER:-}" ] && [ "${VPS_USER}" != CHANGE-ME ]; } || { echo "Set VPS_USER and VPS_HOST in vps.conf."; exit 1; }
OUT="${OUT:-$HOME/Desktop/ArduinoQ/last-vps-check.txt}"
mkdir -p "$(dirname "$OUT")"

IFS= read -r -d '' REDACT <<'PY'
import ipaddress, re, sys
V4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
V6 = re.compile(r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![0-9A-Fa-f:])")
def red(m):
    try:
        return "[public-ip]" if ipaddress.ip_address(m.group(0)).is_global else m.group(0)
    except ValueError:
        return m.group(0)
LOGIN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
TAILNET = re.compile(r"[\w-]+(?:\.[\w-]+)*\.(?:ts\.net|tailscale\.net|tailscale\.com)\b")
for line in sys.stdin:
    line = TAILNET.sub("[tailnet-name]", LOGIN.sub("[login]", line))
    sys.stdout.write(V6.sub(red, V4.sub(red, line)))
PY

IFS= read -r -d '' PROBE <<'REMOTE'
S=""; [ "$(id -u)" -ne 0 ] && S="sudo -n"
t() { command -v "$1" >/dev/null 2>&1; }
r() { echo "R $1=$2"; }
if [ -z "$S" ] || sudo -n true 2>/dev/null; then r root yes; else r root no; S="false"; fi
r fwd4 "$(sysctl -n net.ipv4.ip_forward 2>/dev/null)"
r fwd6 "$(sysctl -n net.ipv6.conf.all.forwarding 2>/dev/null)"
r kernel "$(uname -r)"
WAN="$(ip -4 -o route get 8.8.8.8 2>/dev/null | sed -n 's/.* dev \([^ ]*\).*/\1/p' | head -1)"
r wan "$WAN"
[ -n "$WAN" ] && r wan_mtu "$(cat "/sys/class/net/$WAN/mtu" 2>/dev/null)"
r ts_mtu "$(cat /sys/class/net/tailscale0/mtu 2>/dev/null)"
ping -4 -c1 -W3 1.1.1.1 >/dev/null 2>&1 && r v4_uplink yes || r v4_uplink no
ping -6 -c1 -W3 2001:4860:4860::8888 >/dev/null 2>&1 && r v6_uplink yes || r v6_uplink no
[ -f /var/run/reboot-required ] && r reboot yes || r reboot no
if t ufw; then
  U="$($S ufw status verbose 2>/dev/null)"
  r ufw "$(printf '%s\n' "$U" | sed -n 's/^Status: //p' | head -1)"
  r ufw_default "$(printf '%s\n' "$U" | sed -n 's/^Default: //p' | head -1)"
  r ufw_fwd_policy "$(sed -n 's/^DEFAULT_FORWARD_POLICY=//p' /etc/default/ufw 2>/dev/null | tr -d '"')"
else r ufw none; fi
# Tailscale's OWN rule (chain ts-postrouting), so Docker's masquerade rules cannot satisfy this. Chain names UNVERIFIED against the docs.
r ts_masq "$( ( $S iptables -t nat -S ts-postrouting 2>/dev/null; $S nft list ruleset 2>/dev/null | sed -n '/chain ts-postrouting/,/}/p' ) | grep -ci masquerade)"
[ -n "$WAN" ] && r accept_ra "$(sysctl -n "net.ipv6.conf.$WAN.accept_ra" 2>/dev/null)"
if t docker; then
  r docker_published "$($S docker ps --format '{{.Ports}}' 2>/dev/null | grep -cE '0\.0\.0\.0:|:::')"
  r docker_user_rules "$($S iptables -S DOCKER-USER 2>/dev/null | grep -vcE -- '^-N |-j RETURN')"
  r docker_iptables_off "$(grep -c '"iptables": *false' /etc/docker/daemon.json 2>/dev/null)"
else r docker_published none; fi
if t ethtool && [ -n "$WAN" ]; then r gro "$(ethtool -k "$WAN" 2>/dev/null | sed -n 's/^rx-udp-gro-forwarding: \([a-z]*\).*/\1/p')"; else r gro no-ethtool; fi
if t tailscale; then
  r ts_version "$(tailscale version 2>/dev/null | head -1)"
  tailscale status --json 2>/dev/null | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except ValueError:
    print("R ts_state=unreadable"); sys.exit()
s = d.get("Self") or {}
print("R ts_state=%s" % d.get("BackendState"))
print("R exit_approved=%s" % s.get("ExitNodeOption"))
print("R primary_routes=%s" % ",".join(s.get("PrimaryRoutes") or []))
print("R ts_health=%s" % "; ".join(d.get("Health") or []))
direct = relay = 0
for p in (d.get("Peer") or {}).values():
    if p.get("Online"):
        if p.get("CurAddr"): direct += 1
        elif p.get("Relay"): relay += 1
print("R peers_direct=%d" % direct)
print("R peers_relay=%d" % relay)
'
  P="$(tailscale debug prefs 2>/dev/null || $S tailscale debug prefs 2>/dev/null)"
  if [ -n "$P" ]; then printf '%s\n' "$P" | python3 -c '
import json, sys
try:
    print("R advertised=%s" % ",".join(json.load(sys.stdin).get("AdvertiseRoutes") or []))
except ValueError:
    print("R advertised=unknown")
'; else r advertised unknown; fi
  N="$(tailscale netcheck 2>&1)"
  r udp "$(printf '%s\n' "$N" | sed -n 's/^[[:space:]]*\* UDP: //p' | head -1)"
  r mapping_varies "$(printf '%s\n' "$N" | sed -n 's/^[[:space:]]*\* MappingVariesByDestIP: //p' | head -1)"
  r derp "$(printf '%s\n' "$N" | sed -n 's/^[[:space:]]*\* Nearest DERP: //p' | head -1)"
else r ts_state not-installed; fi
echo "RAW ===== sysctl"; sysctl net.ipv4.ip_forward net.ipv6.conf.all.forwarding 2>&1
echo "RAW ===== ufw status verbose"; $S ufw status verbose 2>&1 | head -30; grep -E '^DEFAULT_FORWARD_POLICY' /etc/default/ufw 2>&1
echo "RAW ===== tailscale netcheck"; tailscale netcheck 2>&1 | head -30
echo "RAW ===== tailscale nat rule"; $S iptables -t nat -S ts-postrouting 2>&1 | head -10; $S nft list ruleset 2>&1 | sed -n '/chain ts-postrouting/,/}/p' | head -20
echo "RAW ===== docker ps"; $S docker ps --format '{{.Ports}}' 2>&1 | head -30
echo "RAW ===== DOCKER-USER"; $S iptables -S DOCKER-USER 2>&1 | head -10
echo "RAW ===== ethtool -k WAN (udp gro)"; ethtool -k "$WAN" 2>&1 | grep -E 'gro|Cannot' | head
echo "RAW ===== links (mtu)"; ip -o link show 2>&1 | sed -n 's/^[0-9]*: \([^:@ ]*\).* mtu \([0-9]*\).*/\1 mtu \2/p'
echo "RAW ===== reboot-required"; cat /var/run/reboot-required.pkgs 2>&1 | head
REMOTE

echo "Asking $VPS_USER@(vps) read-only questions over SSH..."
# shellcheck disable=SC2086
GOT="$(printf '%s\n' "$PROBE" | ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new "$VPS_USER@$VPS_HOST" 'bash -s' 2>&1)" \
  || { echo "Cannot reach the VPS over SSH with your key (no password prompts). Check VPS_USER / VPS_HOST in vps.conf. Output was:"; printf '%s\n' "$GOT" | python3 -c "$REDACT" | head -5; exit 1; }
val() { printf '%s\n' "$GOT" | sed -n "s/^R $1=//p" | head -1; }

REPORT=""
say() { REPORT="$REPORT$*
"; }
ok()   { say "[ OK ] $1"; }
bad()  { say "[FAIL] $1"; [ -n "${2:-}" ] && say "       fix: $2"; return 0; }
warn() { say "[WARN] $1"; [ -n "${2:-}" ] && say "       fix: $2"; return 0; }
unk()  { say "[ ?  ] $1"; }

say "VPS check $(date '+%Y-%m-%d %H:%M')   (read-only; public IPs hidden)"
say ""
say "=== On the VPS ==="
[ "$(val root)" = yes ] || say "(not root and 'sudo -n' is not allowed: checks that need root show ? instead)"
if [ "$(val ts_state)" = not-installed ]; then bad "Tailscale is not installed on the VPS." "curl -fsSL https://tailscale.com/install.sh | sh"
elif [ "$(val ts_state)" = Running ]; then ok "Tailscale is running ($(val ts_version))."
else bad "Tailscale state is '$(val ts_state)', not Running." "sudo tailscale up   (then check: tailscale status)"; fi
if [ -n "$(val ts_health)" ]; then warn "Tailscale itself reports: $(val ts_health)"; else ok "Tailscale reports no health warnings."; fi

if [ "$(val fwd4)" = 1 ]; then ok "IPv4 forwarding is on (needed for an exit node)."
else bad "IPv4 forwarding is off: clients connect but get no internet." "echo 'net.ipv4.ip_forward = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf; sudo sysctl -p /etc/sysctl.d/99-tailscale.conf"; fi
if [ "$(val fwd6)" = 1 ]; then ok "IPv6 forwarding is on."
else warn "IPv6 forwarding is off (Tailscale's docs list it with the IPv4 setting). CARE: turning it on makes the kernel stop accepting router advertisements on an interface that gets its IPv6 by SLAAC (accept_ra=1 means 'only while not forwarding'), so the VPS can lose its IPv6 address/route, and your SSH too if you connect over IPv6. accept_ra on $(val wan) is now '$(val accept_ra)'." "FIRST: echo 'net.ipv6.conf.$(val wan).accept_ra = 2' | sudo tee -a /etc/sysctl.d/99-tailscale.conf   THEN: echo 'net.ipv6.conf.all.forwarding = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf; sudo sysctl -p /etc/sysctl.d/99-tailscale.conf   (accept_ra=2: kernel ip-sysctl docs, not re-read this session; keep a Hostinger console open)"; fi

ADV="$(val advertised)"
case "$ADV" in
  unknown|"") unk "Could not read the advertised routes (UNVERIFIED: 'tailscale debug prefs' is not in the public docs; may need sudo)." ;;
  *) A4=no; A6=no; case ",$ADV," in *,0.0.0.0/0,*) A4=yes;; esac; case ",$ADV," in *,::/0,*) A6=yes;; esac
     if [ $A4 = yes ] && [ $A6 = yes ]; then ok "Advertises both exit routes (0.0.0.0/0 and ::/0)."
     else bad "Does not advertise both exit routes (advertised: ${ADV:-none})." "sudo tailscale set --advertise-exit-node"; fi ;;
esac
case "$(val exit_approved)" in
  True) ok "The exit node is approved (offered and approved)." ;;
  False) bad "Not approved as an exit node yet." "In the admin console: Machines > this device > Edit route settings > Use as exit node  (https://tailscale.com/kb/1103/exit-nodes)" ;;
  *) unk "Could not read the exit-node approval." ;;
esac
case "$(val v6_uplink):$ADV" in
  no:*::/0*) warn "::/0 is advertised but the VPS has no working IPv6 uplink: clients' IPv6 traffic goes nowhere, which looks like 'sometimes no internet'." "Give the VPS working IPv6 in the Hostinger panel, or turn IPv6 off on the client. (UNVERIFIED: whether Tailscale can advertise IPv4 only.)" ;;
  yes:*) ok "The VPS has a working IPv6 uplink." ;;
esac
[ "$(val v4_uplink)" = no ] && bad "The VPS cannot reach the internet over IPv4 (a ping failed)." "Check the Hostinger panel / network; this is not a Tailscale problem." || ok "The VPS has a working IPv4 uplink."

case "$(val ufw)" in
  none) ok "ufw is not installed (no host firewall in the way)." ;;
  "") unk "ufw status unknown (needs root)." ;;
  active) if [ "$(val ufw_fwd_policy)" = ACCEPT ]; then ok "ufw is active and DEFAULT_FORWARD_POLICY is ACCEPT."
          else warn "ufw is active with DEFAULT_FORWARD_POLICY=$(val ufw_fwd_policy): forwarded exit traffic may be dropped (UNVERIFIED: tailscaled also adds its own forward rules)." "sudo ufw route allow in on tailscale0 out on $(val wan)   and   sudo ufw allow in on tailscale0   and   sudo ufw allow 41641/udp" ; fi ;;
  *) ok "ufw is $(val ufw) (default: $(val ufw_default))." ;;
esac
if [ "$(val ts_masq)" -gt 0 ] 2>/dev/null; then ok "Tailscale's own masquerade rule (ts-postrouting) is present, so forwarded traffic leaves with the VPS address."
elif [ "$(val root)" != yes ]; then unk "NAT rules unknown (needs root)."
else bad "No Tailscale masquerade rule (chain ts-postrouting) found: exit traffic would leave with private addresses and be dropped. Docker's own masquerade rules do not count. (UNVERIFIED chain name; none exists either if tailscaled runs with --netfilter-mode=off.)" "sudo systemctl restart tailscaled   (short drop: if you are connected over Tailscale, run it from the Hostinger console; with firewalld: sudo firewall-cmd --permanent --add-masquerade)"; fi
case "$(val docker_published)" in
  "") unk "Docker state unknown (needs root)." ;;
  none) ok "Docker is not installed." ;;
  0) ok "Docker publishes no ports on all addresses." ;;
  *) if [ "$(val ufw)" = active ] && [ "$(val docker_user_rules)" = 0 ] && [ "$(val docker_iptables_off)" = 0 ]; then
       warn "Docker publishes $(val docker_published) port(s) on all addresses and there are no DOCKER-USER rules: Docker's own rules bypass ufw, so these are open to the internet whatever ufw says." "Publish on loopback instead (ports: \"127.0.0.1:HOST:CONTAINER\" in compose) or add DOCKER-USER rules"
     else ok "Docker publishes $(val docker_published) port(s) on all addresses; DOCKER-USER rules or iptables=false exist, or ufw is not active (read the RAW section)."; fi ;;
esac
case "$(val gro)" in
  on) ok "UDP GRO forwarding is on for $(val wan) (the Tailscale-documented exit-node speed fix)." ;;
  off) warn "UDP GRO forwarding is off on $(val wan): exit-node throughput is lower than it could be (needs Tailscale 1.54+ and Linux 6.2+; this VPS: kernel $(val kernel))." "sudo ethtool -K $(val wan) rx-udp-gro-forwarding on rx-gro-list off   (some drivers blip the link for a second: use the Hostinger console if SSH runs over this NIC; make it stick: https://tailscale.com/kb/1320/performance-best-practices)" ;;
  no-ethtool) warn "ethtool is not installed, so UDP GRO could not be checked." "sudo apt install ethtool" ;;
  *) unk "UDP GRO forwarding setting not available on $(val wan) (old kernel or virtual NIC without the feature)." ;;
esac
if [ -z "$(val udp)" ]; then unk "netcheck gave no answer (is Tailscale installed and running?)."
elif [ "$(val udp)" = true ]; then ok "UDP works from the VPS (netcheck); nearest relay: $(val derp)."
else warn "netcheck says UDP: '$(val udp)': direct connections are unlikely, traffic would use relays." "Allow outbound UDP; open inbound UDP 41641 in ufw and in the Hostinger firewall."; fi
[ "$(val mapping_varies)" = true ] && warn "The VPS NAT mapping varies by destination (hard NAT), so direct links are harder." ""
WANMTU="$(val wan_mtu)"
if [ -n "$WANMTU" ] && [ "$WANMTU" -lt 1360 ] 2>/dev/null; then say "[WARN] $(val wan) MTU is $WANMTU and tailscale0 is $(val ts_mtu): a 1280-byte tunnel needs about 1360 underneath. No fix is printed on purpose: look at the MTU the provider states in the Hostinger panel and test the path (ping -M do -s SIZE 1.1.1.1, lowering SIZE until it passes; packet size is SIZE+28) before changing anything."
else say "[info] $(val wan) MTU is ${WANMTU:-unknown}, tailscale0 MTU is '$(val ts_mtu)'. If big downloads stall while small pages load, MTU is the thing to look at."; fi
D="$(val peers_direct)"; R="$(val peers_relay)"
if [ "${R:-0}" -gt 0 ] 2>/dev/null && [ "${D:-0}" = 0 ]; then warn "Online devices reach the VPS only through relays (direct $D, relayed $R): slow and stalls when roaming." "Open UDP 41641 inbound on the VPS firewall and in Hostinger's firewall (see netcheck)."
else say "[info] Online devices: $D direct, $R via relay."; fi
[ "$(val reboot)" = yes ] && warn "The VPS needs a reboot (pending updates)." "sudo reboot   (SSH drops for a minute and the exit node is offline; do it when you are not relying on it)" || ok "No reboot pending."

say ""
say "=== On this Mac ==="
TS="$(command -v tailscale || true)"
[ -z "$TS" ] && [ -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ] && TS=/Applications/Tailscale.app/Contents/MacOS/Tailscale
if [ -z "$TS" ]; then unk "Tailscale command not found on this Mac; skipped."; else
  MAC="$("$TS" status --json 2>/dev/null | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except ValueError:
    print("unreadable"); sys.exit()
print("on" if d.get("ExitNodeStatus") else "off")
' 2>/dev/null)"
  LAN="$("$TS" debug prefs 2>/dev/null | sed -n 's/.*"ExitNodeAllowLANAccess": *\([a-z]*\).*/\1/p' | head -1)"
  DNS="$("$TS" dns status 2>&1 | grep -Eo '[0-9]{1,3}([.][0-9]{1,3}){3}' | sort -u | tr '\n' ' ')"
  case "$MAC" in
    on) say "[info] An exit node is selected on this Mac."
        say "[WARN] With an exit node on, this Mac uses the EXIT NODE as its DNS resolver for all domains, so the board is bypassed unless its nameserver has 'Use with exit node' ticked."
        say "       fix: admin console > DNS > the nameserver entry for the board > tick 'Use with exit node'  (https://tailscale.com/kb/1054/dns)" ;;
    off) say "[info] No exit node is selected on this Mac right now (turn it on, run this again to see it under load)." ;;
    *) unk "Could not read the exit-node state." ;;
  esac
  case "$LAN" in
    true) [ "$MAC" = on ] && warn "'Allow local network access' is ON while using the exit node: traffic to the local (building) network bypasses the exit node and this Mac talks directly to untrusted devices there (Tailscale: it creates an exception for your LAN only; https://tailscale.com/kb/1103/exit-nodes)." "tailscale set --exit-node-allow-lan-access=false   (or untick it in the menu bar app)" || say "[info] 'Allow local network access' is on (matters only while an exit node is selected)." ;;
    false) ok "'Allow local network access' is off: all traffic, including to the local network, goes through the exit node (local printers will not be reachable while it is on)." ;;
    *) unk "Could not read 'Allow local network access' (UNVERIFIED: 'tailscale debug prefs' / field ExitNodeAllowLANAccess; check in the menu bar app)." ;;
  esac
  say "[info] Addresses in 'tailscale dns status' (names are not saved here): ${DNS:-none found}. The board's Tailscale address should be among them."
fi
say ""
say "=== Raw output from the VPS (device names and logins are not collected; the tailnet name is stripped) ==="
say "None of the fixes above touches sshd or removes a firewall rule; the ones that can interrupt a session say so."
say "$(printf '%s\n' "$GOT" | sed -n '/^RAW =====/,$p' | sed 's/^RAW =====/-----/')"

printf '%s' "$REPORT" | python3 -c "$REDACT" | tee "$OUT"
echo
echo "Saved to $OUT (public IPs hidden). Nothing was changed on the VPS."
