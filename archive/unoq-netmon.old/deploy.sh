#!/usr/bin/env bash
# Run on your laptop from this folder:  ./deploy.sh arduino@100.69.33.51 [--dns]
set -e
BOARD="${1:?usage: ./deploy.sh user@board-ip [--dns]}"; MODE="${2:-}"; HOST="${BOARD#*@}"
CP="/tmp/overheard-$$"; O="-o ControlMaster=auto -o ControlPath=$CP -o ControlPersist=120"   # one password prompt
ssh $O "$BOARD" 'mkdir -p ~/netmon && pkill -f netmon/agent.py; sudo pkill -f "agent.py" 2>/dev/null; true'
scp $O agent/agent.py agent/dashboard.html "$BOARD:~/netmon/"
if [ "$MODE" = "--dns" ]; then
  ssh -t $O "$BOARD" "cd ~/netmon && sudo sh -c 'nohup python3 agent.py --dns > agent.log 2>&1 < /dev/null &'"
else
  ssh $O "$BOARD" "cd ~/netmon && nohup python3 agent.py > agent.log 2>&1 < /dev/null &"
fi
sleep 3; echo "Dashboard: http://$HOST:8080"; open "http://$HOST:8080" 2>/dev/null || true
