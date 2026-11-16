#!/usr/bin/env bash
# Connects to the board, sends the program, starts it, opens the dashboard. Ctrl+C stops it.
set -e
cd "$(dirname "$0")"
BOARD="${BOARD:-arduino@100.69.33.51}"; HOST="${BOARD#*@}"
O="-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8"
ssh $O "$BOARD" true 2>/dev/null || { echo "Can't reach the board without a password. First time? Run: bash setup.sh"; exit 1; }
ssh $O "$BOARD" "pkill -f '[a]gent.py' || true; mkdir -p ~/netmon"
scp -q $O agent/agent.py agent/dashboard.html "$BOARD:~/netmon/"
(sleep 7; open "http://$HOST:8080") >/dev/null 2>&1 &
echo "Overheard is running on the board. Dashboard: http://$HOST:8080   (Ctrl+C to stop)"
exec ssh -t $O "$BOARD" "cd ~/netmon && python3 agent.py --dns --bind $HOST"
