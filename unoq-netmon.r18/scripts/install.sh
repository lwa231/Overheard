#!/usr/bin/env bash
# Installs Overheard on the board as a service: starts at boot, restarts if it stops, survives closing the terminal.
# Needs the board's sudo password once. Run from the Mac:  bash scripts/install.sh
set -euo pipefail
cd "$(dirname "$0")/.."
. "$(dirname "${BASH_SOURCE[0]}")/board.sh" || exit 1
BOARD="${BOARD:-}"
if [ -z "$BOARD" ]; then
  if nc -z -G 3 "$BOARD_HOST" 22 >/dev/null 2>&1; then BOARD="$BOARD_DEFAULT"
  elif ping -c1 -t3 "$BOARD_MDNS" >/dev/null 2>&1; then BOARD="$BOARD_USER@$BOARD_MDNS"
  else echo "Cannot find the board on this network. Is it powered and on the same Wi-Fi? You can also run: BOARD=arduino@<its address> bash $0"; exit 1; fi
fi
# Extra networks allowed to use the DNS server (the defaults are the private and Tailscale ranges). Nothing is allowed by default:
#   ALLOW_EXTRA=a,b   adds to what the board already has        ALLOW_EXTRA=none   clears all extras
# The address this Mac has as the board sees it is added automatically when it is outside the defaults.
ALLOW_EXTRA="${ALLOW_EXTRA:-}"
if [ "$ALLOW_EXTRA" != none ]; then
  case "$ALLOW_EXTRA" in *[!0-9a-fA-F:./,]*) echo "ALLOW_EXTRA must be comma separated addresses like 203.0.113.7/32, or none"; exit 1;; esac
fi
O="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"
SEEN="$(ssh $O "$BOARD" 'echo "prev=$(sed -n "s/.*--allow-extra \([^ ]*\).*/\1/p" /etc/systemd/system/overheard.service 2>/dev/null | head -1)"; echo "mac=${SSH_CLIENT%% *}"')" || { echo "Cannot reach the board over SSH."; exit 1; }
PREV="$(printf '%s\n' "$SEEN" | sed -n 's/^prev=//p')"
MAC="$(printf '%s\n' "$SEEN" | sed -n 's/^mac=//p')"
case "$PREV$MAC" in *[!0-9a-fA-F:./,]*) echo "Unexpected answer from the board: $SEEN"; exit 1;; esac
echo "Sending the program to the board..."
ssh $O "$BOARD" "mkdir -p ~/netmon/data && rm -rf ~/netmon/overheard"
tar -C src --exclude __pycache__ -cf - overheard | ssh $O "$BOARD" "tar -C ~/netmon -xf -"
# The board works out the final list with the program's own default ranges.
RESULT="$(ssh $O "$BOARD" "PYTHONPATH=\$HOME/netmon python3 - '$PREV' '$ALLOW_EXTRA' '$MAC'" <<'PY'
import ipaddress
import sys

from overheard.config import Config

prev, want, mac = sys.argv[1:4]
nets = [] if want == "none" else [x for x in (prev + "," + want).split(",") if x]
if want != "none" and mac:
    ip = ipaddress.ip_address(mac)
    if not any(ip in ipaddress.ip_network(d) for d in Config.allow):
        nets.append(mac + ("/128" if ip.version == 6 else "/32"))
        print("added=" + mac)
final = []
for n in nets:
    n = str(ipaddress.ip_network(n, strict=False))
    if n not in final:
        final.append(n)
print("final=" + ",".join(final))
PY
)" || { echo "Could not work out the allowed networks (bad ALLOW_EXTRA?)."; exit 1; }
FINAL="$(printf '%s\n' "$RESULT" | sed -n 's/^final=//p')"
case "$FINAL" in *[!0-9a-fA-F:./,]*) echo "Unexpected answer from the board: $RESULT"; exit 1;; esac
EXTRA=""
[ -n "$FINAL" ] && EXTRA=" --allow-extra $FINAL"
if [ "${NO_TLS:-}" = "1" ]; then
  EXTRA="$EXTRA --no-tls"
  echo "NO_TLS=1: upstream lookups will go out unencrypted."
fi
echo "Board sees this Mac as: ${MAC:-unknown}"
printf '%s\n' "$RESULT" | sed -n 's/^added=\(.*\)/Added automatically (outside the default ranges): \1/p'
echo "Allowed to use the DNS server: private and Tailscale ranges${FINAL:+ plus $FINAL}"
echo "Installing the service (asks for the board's sudo password once)..."
ssh -t $O "$BOARD" 'sudo bash -c "
cat > /etc/systemd/system/overheard.service <<UNIT
[Unit]
Description=Overheard DNS filter and network monitor
After=network-online.target
Wants=network-online.target

[Service]
User=arduino
WorkingDirectory=/home/arduino/netmon
Environment=PYTHONPATH=/home/arduino/netmon
ExecStart=/usr/bin/python3 -m overheard --dns --bind 0.0.0.0 --data-dir /home/arduino/netmon/data --profile-all'"$EXTRA"'
AmbientCapabilities=CAP_NET_BIND_SERVICE
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
systemctl stop overheard.service 2>/dev/null || true
pkill -f \"^(/usr/bin/)?python3 -m overheard\" || true
systemctl daemon-reload
systemctl enable --now overheard.service
sleep 4
systemctl --no-pager --lines=8 status overheard.service || true
"'
echo
bash "$(dirname "$0")/status.sh"
