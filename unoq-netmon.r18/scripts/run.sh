#!/usr/bin/env bash
# Sends the program to the board, starts it, opens the dashboard. Ctrl+C stops it.
set -euo pipefail
cd "$(dirname "$0")/.."
. "$(dirname "${BASH_SOURCE[0]}")/board.sh" || exit 1
BOARD="${BOARD:-$BOARD_DEFAULT}"; HOST="${BOARD#*@}"
O="-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8"
ssh $O "$BOARD" true 2>/dev/null || { echo "Can't reach the board without a password. First time? Run: bash scripts/setup.sh"; exit 1; }
ssh $O "$BOARD" "systemctl is-active -q overheard.service" 2>/dev/null && { echo "Overheard is already installed as a service on the board and running. Use Check Overheard.command, or reinstall with Install Overheard.command."; exit 0; }
ssh $O "$BOARD" "pkill -f '^(/usr/bin/)?python3 -m overheard' || true; mkdir -p ~/netmon/data && [ -f ~/netmon/blocklist.txt ] && [ ! -f ~/netmon/data/blocklist.txt ] && mv ~/netmon/blocklist.txt ~/netmon/data/ || true"
tar -C src --exclude __pycache__ -cf - overheard | ssh $O "$BOARD" "rm -rf ~/netmon/overheard && tar -C ~/netmon -xf -"
(
  for _ in $(seq 1 90); do
    curl -fsS -m 2 "http://$HOST:8080/api/health" >/dev/null 2>&1 && break
    sleep 1
  done
  KEY="$(ssh $O "$BOARD" 'cat ~/netmon/data/token' 2>/dev/null || true)"
  echo "Dashboard is up. Opening it in your browser."
  open "http://$HOST:8080/?key=$KEY"
) &
echo "Starting Overheard on the board. This takes up to a minute the first time. The dashboard opens by itself when it is ready.   (Ctrl+C to stop)"
exec ssh -t $O "$BOARD" "cd ~/netmon && PYTHONPATH=. python3 -m overheard --dns --bind 0.0.0.0 --data-dir ~/netmon/data --profile-all"
