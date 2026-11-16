#!/usr/bin/env bash
# Installs Overheard on the board as a service: starts at boot, restarts if it stops, survives closing the terminal.
# Needs the board's sudo password once. Run from the Mac:  bash scripts/install.sh
set -euo pipefail
cd "$(dirname "$0")/.."
BOARD="${BOARD:-}"
if [ -z "$BOARD" ]; then
  if nc -z -G 3 100.69.33.51 22 >/dev/null 2>&1; then BOARD="arduino@100.69.33.51"
  elif ping -c1 -t3 UnoQ1.local >/dev/null 2>&1; then BOARD="arduino@UnoQ1.local"
  else echo "Cannot find the board on this network. Is it powered and on the same Wi-Fi? You can also run: BOARD=arduino@<its address> bash $0"; exit 1; fi
fi
ALLOW_EXTRA="${ALLOW_EXTRA:-203.0.113.0/24}"
NO_TLS="${NO_TLS:-1}"
EXTRA=""
if [ -n "${ALLOW_EXTRA:-}" ]; then
  case "$ALLOW_EXTRA" in *[!0-9a-fA-F:./,]*) echo "ALLOW_EXTRA must be comma separated addresses like 203.0.113.254/32"; exit 1;; esac
  EXTRA=" --allow-extra $ALLOW_EXTRA"
fi
if [ "${NO_TLS:-}" = "1" ]; then
  EXTRA="$EXTRA --no-tls"
fi
O="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"
echo "Sending the program to the board..."
ssh $O "$BOARD" "mkdir -p ~/netmon/data && rm -rf ~/netmon/overheard"
tar -C src --exclude __pycache__ -cf - overheard | ssh $O "$BOARD" "tar -C ~/netmon -xf -"
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
