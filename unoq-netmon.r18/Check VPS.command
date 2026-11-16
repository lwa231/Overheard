#!/usr/bin/env bash
# Double-click me to check the exit-node VPS (read-only: nothing is changed there). Needs vps.conf (copy vps.conf.example).
cd "$(dirname "$0")" || exit 1
bash scripts/vps_check.sh 2>&1
echo
echo "Saved to ~/Desktop/ArduinoQ/last-vps-check.txt (public addresses hidden; send it to Claude)."
read -r -p "Press Return to close. "
