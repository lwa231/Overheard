#!/usr/bin/env bash
# Double-click me. Apple profiles can't set plain DNS, so this writes manual iPhone steps (and a profile only if the board serves DoT).
cd "$(dirname "$0")" || exit 1
python3 tools/make_profile.py "$@"
echo
echo "Next: open ~/Desktop/ArduinoQ/iPhone-DNS-steps.txt and follow it (AirDrop it to the phone if you like)."
read -r -p "Press Return to close. "
