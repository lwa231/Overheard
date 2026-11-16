#!/usr/bin/env bash
# Gives the board's current Wi-Fi connection a fixed IPv4 address (NetworkManager only), with an automatic way back.
# Run from the Mac:  bash scripts/net_static.sh              apply
#                    bash scripts/net_static.sh --dry-run    print the commands, touch nothing (does not even contact the board)
#                    bash scripts/net_static.sh --revert     back to DHCP (also what the 90 s safety timer does)
# Values come from the site conf (see sites/home.conf.example):  BOARD_LAN_IP=10.10.50.2/24   BOARD_LAN_GW=10.10.50.1
# Lock-out safety: it only runs over the board's TAILSCALE address (a LAN address stops working the moment it changes),
# checks Tailscale is up first, and arms a timer on the board that returns the connection to DHCP after 90 s unless a NEW ssh
# connection from this Mac, made while the timer is still safely pending (checked on the board's own clock, 80 s after arming), finds
# the board healthy: new address present, gateway pings, a name resolves, Tailscale running.
# The board's own DNS becomes 127.0.0.1 (Overheard) with 9.9.9.9 as a fallback for the BOARD's own lookups only; clients never get it.
# Asks for the board's sudo password once. UNTESTED on a real UNO Q.
set -u
. "$(dirname "${BASH_SOURCE[0]}")/board.sh" || exit 1
. "$(dirname "${BASH_SOURCE[0]}")/lan.sh"
MODE=apply
case "${1:-}" in
  "") ;;
  --dry-run) MODE=dry ;;
  --revert) MODE=revert ;;
  *) echo "Usage: bash scripts/net_static.sh [--dry-run | --revert]"; exit 1 ;;
esac

if [ "$MODE" != revert ]; then
  LAN_IP="${BOARD_LAN_IP:-}"; LAN_GW="${BOARD_LAN_GW:-}"
  if [ -z "$LAN_IP" ] || [ -z "$LAN_GW" ]; then
    echo "Add two lines to this board's site file (sites/<name>.conf), for example:"
    echo "  BOARD_LAN_IP=10.10.50.2/24"
    echo "  BOARD_LAN_GW=10.10.50.1"
    exit 1
  fi
  lan_cidr_ok "$LAN_IP" || { echo "BOARD_LAN_IP must be an IPv4 host address with a prefix length of 8 to 30 (not the network or broadcast address), like 10.10.50.2/24; got: $LAN_IP"; exit 1; }
  ip_ok "$LAN_GW" || { echo "BOARD_LAN_GW is not an IPv4 address: $LAN_GW"; exit 1; }
  lan_gw_ok "$LAN_IP" "$LAN_GW" || { echo "BOARD_LAN_GW $LAN_GW must be inside the same subnet as $LAN_IP, and not the board's own address, the network address or the broadcast address."; exit 1; }
fi

SET_TPL() { echo "nmcli connection modify uuid $1 ipv4.method manual ipv4.addresses $LAN_IP ipv4.gateway $LAN_GW ipv4.dns 127.0.0.1,9.9.9.9"; }
BACK_TPL() { echo "nmcli connection modify uuid $1 ipv4.method auto ipv4.addresses '' ipv4.gateway '' ipv4.dns ''"; }
UP_TPL() { echo "nmcli connection up uuid $1"; }

if [ "$MODE" = dry ]; then
  U="<uuid of the current Wi-Fi connection>"
  echo "Dry run: nothing is contacted or changed. A real run first checks, over SSH on the board's Tailscale address:"
  echo "  NetworkManager is the network manager (otherwise it stops), systemd-run exists, Tailscale is running, and BOARD_HOST is the board's Tailscale address."
  echo "Then, as root on the board (asks for the sudo password once):"
  echo "  systemd-run --unit=overheard-netrevert --on-active=90 ...    # safety timer: at 90 s runs the two lines below unless the Mac confirmed"
  echo "    $(BACK_TPL "$U")"
  echo "    $(UP_TPL "$U")"
  echo "  $(SET_TPL "$U")"
  echo "  $(UP_TPL "$U")"
  echo "The board's own DNS: 127.0.0.1 (Overheard), then 9.9.9.9 (plain) so the BOARD can still resolve names when Overheard is down. Clients never get 9.9.9.9."
  echo "Then, over a brand-new SSH connection from this Mac: new address present, ping $LAN_GW from the board, a name resolves, Tailscale running, and fewer than 80 s since the timer was armed; only then confirm (cancels the revert)."
  exit 0
fi

BOARD="${BOARD:-$BOARD_DEFAULT}"
HOST="${BOARD#*@}"
O="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 -o BatchMode=yes"
echo "Looking at the board ($BOARD), read-only..."
IFS= read -r -d '' PROBE_SH <<'REMOTE'
echo "nm=$(systemctl is-active NetworkManager 2>/dev/null)"
echo "networkd=$(systemctl is-active systemd-networkd 2>/dev/null)"
echo "ifupdown=$( [ -s /etc/network/interfaces ] && grep -qE '^(auto|iface) w' /etc/network/interfaces && echo yes || echo no)"
echo "sdrun=$(command -v systemd-run >/dev/null 2>&1 && echo yes || echo no)"
if command -v nmcli >/dev/null 2>&1; then
  dev=$(nmcli -t -f DEVICE,TYPE,STATE device status 2>/dev/null | awk -F: '$2=="wifi" && $3=="connected"{print $1; exit}')
  echo "dev=$dev"
  [ -n "$dev" ] && { echo "uuid=$(nmcli -g GENERAL.CON-UUID device show "$dev" 2>/dev/null)"; echo "con=$(nmcli -g GENERAL.CONNECTION device show "$dev" 2>/dev/null)"; echo "ipnow=$(nmcli -g IP4.ADDRESS device show "$dev" 2>/dev/null | head -1)"; }
fi
if command -v tailscale >/dev/null 2>&1; then
  echo "tsip=$(tailscale ip -4 2>/dev/null | head -1)"
  echo "tsstate=$(tailscale status --json 2>/dev/null | sed -n 's/.*"BackendState": *"\([^"]*\)".*/\1/p' | head -1)"
fi
REMOTE
# shellcheck disable=SC2086
PROBE="$(printf '%s\n' "$PROBE_SH" | ssh $O "$BOARD" 'bash -s')" || { echo "Cannot reach the board over SSH with the key (no password prompts here). Run scripts/setup.sh once, and check BOARD_HOST in the site file."; exit 1; }
val() { printf '%s\n' "$PROBE" | sed -n "s/^$1=//p" | head -1; }

if [ "$(val nm)" != active ]; then
  echo "STOP: NetworkManager is not running on this board (NetworkManager=$(val nm), systemd-networkd=$(val networkd), ifupdown=$(val ifupdown))."
  echo "This script only knows NetworkManager and will not guess configs for the others. Set the address by hand, or send this output to Claude."
  echo "(UNVERIFIED on a real UNO Q: which one it uses.)"
  exit 1
fi
UUID="$(val uuid)"; CON="$(val con)"
case "$UUID" in *[!0-9a-f-]*|"") echo "STOP: no connected Wi-Fi connection found on the board (dev='$(val dev)'). Is it on Wi-Fi?"; exit 1;; esac
[ "${#UUID}" -eq 36 ] || { echo "STOP: unexpected connection id from the board: $UUID"; exit 1; }
TSIP="$(val tsip)"
if [ "$(val tsstate)" != Running ] || [ -z "$TSIP" ]; then
  echo "STOP: Tailscale is not running on the board (state: '$(val tsstate)'). Fix that first: a fixed address without a way back in can lock you out."
  exit 1
fi
if [ "$HOST" != "$TSIP" ]; then
  echo "STOP: you reached the board as $HOST, but its Tailscale address is $TSIP."
  echo "A LAN address stops working when the address changes. Put BOARD_HOST=$TSIP in the site file (or run: BOARD_HOST=$TSIP bash $0 ...) and try again."
  exit 1
fi
if [ "$MODE" = apply ] && [ "$(val sdrun)" != yes ]; then
  echo "STOP: systemd-run is not available on the board, so the safety timer cannot be armed. Nothing was changed."
  exit 1
fi
echo "Wi-Fi connection: '$CON' ($UUID), address now: $(val ipnow). Tailscale: running at $TSIP."

SET="$(SET_TPL "$UUID")"; BACK="$(BACK_TPL "$UUID")"; UP="$(UP_TPL "$UUID")"
if [ "$MODE" = revert ]; then
  echo "Will set the connection back to DHCP. Asks for the board's sudo password once."
  read -r -p "Press Return to continue, Ctrl-C to stop. "
  # shellcheck disable=SC2086
  ssh -t $O -o ServerAliveInterval=5 "$BOARD" "sudo bash -c $(printf '%q' "$BACK && $UP")"
  echo "Done. The board gets an address from the router again; find it with: ssh $BOARD hostname -I"
  exit 0
fi

echo "Will give the board $LAN_IP (gateway $LAN_GW; its own DNS: itself, then 9.9.9.9 for the board's own lookups only). Asks for the board's sudo password once."
echo "Safety: if a fresh SSH connection from this Mac cannot confirm the board is fine within 80 s of the timer being armed, the board goes back to DHCP by itself."
read -r -p "Press Return to continue, Ctrl-C to stop. "
IFS= read -r -d '' APPLY <<EOF
set -e
command -v systemd-run >/dev/null || { echo "systemd-run is not installed: nothing was changed."; exit 3; }
OK="\$(getent passwd "\$SUDO_USER" | cut -d: -f6)/.overheard-net-ok"
rm -f "\$OK" /run/overheard-netrevert.armed
cat > /run/overheard-netrevert.sh <<'EOS'
#!/bin/sh
[ -e "\$1" ] && exit 0
$BACK
$UP
EOS
chmod 700 /run/overheard-netrevert.sh
systemctl stop overheard-netrevert.timer 2>/dev/null || true
systemd-run --quiet --unit=overheard-netrevert --on-active=90 --collect /bin/sh /run/overheard-netrevert.sh "\$OK" || { echo "Could not arm the safety timer: nothing was changed."; exit 4; }
cut -d' ' -f1 /proc/uptime > /run/overheard-netrevert.armed
echo "Safety timer armed (90 s). Applying now; this SSH session may pause while the address changes."
$SET
$UP
EOF
# The confirmation: one brand-new SSH connection, run on the board. Exit 0 = healthy and confirmed in time, 1 = not healthy (yet),
# 3 = healthy but too late (the timer has, or is about to have, fired), 4 = the timer was never armed.
IFS= read -r -d '' CHECK <<EOF
a=\$(cat /run/overheard-netrevert.armed 2>/dev/null) || exit 4
ip -4 -o addr | grep -q ' ${LAN_IP%/*}/' || exit 1
ping -c1 -W2 $LAN_GW >/dev/null 2>&1 || exit 1
getent hosts example.com >/dev/null 2>&1 || exit 1
tailscale status --json 2>/dev/null | grep -Eq '"BackendState": *"Running"' || exit 1
u=\$(cut -d' ' -f1 /proc/uptime)
awk -v a="\$a" -v u="\$u" 'BEGIN{exit !(u-a < 80)}' || exit 3
touch ~/.overheard-net-ok
EOF
T0=$SECONDS                                  # the clock starts before the apply, not after it returns
# shellcheck disable=SC2086
ssh -t $O -o ServerAliveInterval=5 "$BOARD" "sudo bash -c $(printf '%q' "$APPLY")"; RC=$?
case "$RC" in
  3|4) echo "Nothing was changed on the board (it said so above). Fix that and run this again."; exit 1 ;;
  0) ;;
  *) echo "(the SSH session ended with status $RC; checking from here)" ;;
esac

echo "Checking, over a new connection, that the board is still reachable and healthy..."
GOOD=""; LATE=""
while [ $((SECONDS - T0)) -lt 180 ]; do
  sleep "${NET_STATIC_POLL:-5}"      # (tests shorten it)
  # shellcheck disable=SC2086
  printf '%s\n' "$CHECK" | ssh $O -o ControlPath=none -o ControlMaster=no "$BOARD" 'bash -s' 2>/dev/null; R=$?
  case "$R" in
    0) GOOD=1; break ;;
    3) LATE=1; break ;;
    4) break ;;
  esac
  printf '.'
done
echo
if [ -n "$GOOD" ]; then
  echo "OK: the board has ${LAN_IP%/*}, reaches $LAN_GW, resolves names and Tailscale is running. Confirmed before the deadline; the revert timer will do nothing."
  echo "Next: reserve ${LAN_IP%/*} for the board's Wi-Fi MAC on the router, so the two agree."
elif [ -n "$LATE" ]; then
  echo "NOT confirmed in time: the board looked healthy only after the safety timer's deadline, so it has gone (or is about to go) back to DHCP."
  echo "Check where it is: ssh $BOARD 'ip -4 -o addr'. Run this script again if you still want the fixed address."
  exit 1
else
  echo "NOT confirmed. If the timer was armed, the board returns to DHCP by itself about 90 s after arming and is reachable on Tailscale again;"
  echo "wait 2 minutes, then check: ssh $BOARD 'ip -4 -o addr'. If it is not reachable at all, power-cycle it: it comes up on DHCP with the service running."
  echo "Send this output to Claude."
  exit 1
fi
