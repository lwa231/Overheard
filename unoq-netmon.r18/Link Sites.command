#!/usr/bin/env bash
# Double-click me to link the boards (home, apartment, ...) so each dashboard can show the others.
# Needs sites/<name>.conf for every board. Asks for each board's sudo password once, to restart it.
cd "$(dirname "$0")" || exit 1
bash scripts/link_sites.sh
read -r -p "Press Return to close. "
