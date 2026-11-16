#!/usr/bin/env bash
# Double-click me to put Tailscale on the board, so the server can reach Overheard.
# You will be asked for the board's password, then shown a link to open and sign in.
cd "$(dirname "$0")" || exit 1
. scripts/board.sh || exit 1
BOARD="${BOARD:-$BOARD_DEFAULT}"
mkdir -p ~/Desktop/ArduinoQ
ssh -t "$BOARD" 'command -v tailscale >/dev/null || curl -fsSL https://tailscale.com/install.sh | sh; sudo tailscale up'
{ date; ssh "$BOARD" 'tailscale ip -4; tailscale status' 2>&1; } | tee ~/Desktop/ArduinoQ/last-tailscale.txt
echo
echo "Saved to ~/Desktop/ArduinoQ/last-tailscale.txt (Claude reads it)."
read -r -p "Press Return to close. "
