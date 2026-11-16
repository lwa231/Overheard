#!/usr/bin/env bash
# Double-click me, then open http://phonetest.example.com on the phone. Tells you whether the phone's lookup reached the board.
cd "$(dirname "$0")" || exit 1
mkdir -p ~/Desktop/ArduinoQ
. scripts/board.sh || { read -r -p "Press Return to close. "; exit 1; }
BOARD="${BOARD:-}"
if [ -z "$BOARD" ]; then
  if nc -z -G 3 "$BOARD_HOST" 22 >/dev/null 2>&1; then BOARD="$BOARD_DEFAULT"
  elif ping -c1 -t3 "$BOARD_MDNS" >/dev/null 2>&1; then BOARD="$BOARD_USER@$BOARD_MDNS"
  else echo "Cannot find the board on this network. Is it powered and on the same Wi-Fi?"; read -r -p "Press Return to close. "; exit 1; fi
fi
{
  date
  ssh -o ConnectTimeout=10 "$BOARD" 'cd ~/netmon && PYTHONPATH=$HOME/netmon python3 -m overheard.doctor --seconds 90' 2>&1
} | tee ~/Desktop/ArduinoQ/last-phone-test.txt
echo
echo "Saved to ~/Desktop/ArduinoQ/last-phone-test.txt (send it to Claude if it says refused or never arrived)."
read -r -p "Press Return to close. "
