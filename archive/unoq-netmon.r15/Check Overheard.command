#!/usr/bin/env bash
# Double-click me to see whether the board is running Overheard and what address to use as DNS.
cd "$(dirname "$0")" || exit 1
bash scripts/status.sh
read -r -p "Press Return to close. "
