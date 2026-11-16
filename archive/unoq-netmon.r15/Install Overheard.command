#!/usr/bin/env bash
# Double-click me. Installs/updates Overheard on the board and checks that it works.
cd "$(dirname "$0")" || exit 1
export ALLOW_EXTRA="${ALLOW_EXTRA:-203.0.113.0/24}"
export NO_TLS="${NO_TLS:-1}"
if bash scripts/install.sh; then
  echo
  echo "Done. You can close this window."
else
  echo
  echo "Install FAILED. Read the messages above, then send them to Claude."
fi
read -r -p "Press Return to close. "
