#!/usr/bin/env bash
# Double-click me to give the board a fixed address on the router's Wi-Fi (BOARD_LAN_IP / BOARD_LAN_GW in its sites/*.conf).
# It checks Tailscale first, asks for the board's sudo password once, and puts the board back on DHCP by itself if it cannot confirm the change.
cd "$(dirname "$0")" || exit 1
mkdir -p ~/Desktop/ArduinoQ
{ date; bash scripts/net_static.sh 2>&1; } | tee ~/Desktop/ArduinoQ/last-address.txt
echo
echo "Saved to ~/Desktop/ArduinoQ/last-address.txt (send it to Claude if something is wrong)."
read -r -p "Press Return to close. "
