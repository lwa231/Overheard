#!/usr/bin/env bash
# Double-click me. Installs/updates Overheard on the board and checks that it works.
cd "$(dirname "$0")" || exit 1
if bash scripts/install.sh; then
  echo
  echo "Done. You can close this window."
else
  echo
  echo "Install FAILED. Read the messages above, then send them to Claude."
fi
read -r -p "Press Return to close. "
