#!/usr/bin/env bash
# Double-click me to see whether the board is running Overheard and what address to use as DNS.
cd "$(dirname "$0")" || exit 1
mkdir -p ~/Desktop/ArduinoQ
{ date; bash scripts/status.sh 2>&1; } | tee ~/Desktop/ArduinoQ/last-check.txt
echo
echo "Saved to ~/Desktop/ArduinoQ/last-check.txt (send it to Claude if something is wrong)."
read -r -p "Press Return to close. "
