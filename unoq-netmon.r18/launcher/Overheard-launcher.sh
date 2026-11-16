#!/bin/bash
# One-click dashboard opener that follows board.conf. To use it: copy this file over
# Overheard.app/Contents/MacOS/Overheard (keep it executable), or run it directly.
# Pick another board with:  SITE=home  (a file in sites/)  or  BOARD_HOST=<address>.
ROOT="${OVERHEARD_DIR:-$HOME/Desktop/ArduinoQ/unoq-netmon.r18}"
# shellcheck disable=SC1091
. "$ROOT/scripts/board.sh" || { osascript -e 'display alert "Overheard" message "Set BOARD_HOST in board.conf." as warning'; exit 1; }
TOKEN=$(ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new "$BOARD_DEFAULT" 'cat ~/netmon/data/token' 2>/dev/null)
if [ -z "$TOKEN" ]; then
  osascript -e 'display alert "Overheard" message "Cannot reach the board. Is it powered on and on the same network?" as warning'
  exit 1
fi
open "http://$BOARD_HOST:8080/?key=$TOKEN"
