#!/usr/bin/env bash
# Double-click me to prepare the LED matrix sketch for Arduino App Lab (USB route).
# Nothing in this project installs the LED app automatically, so this opens the app folder and prints the steps.
cd "$(dirname "$0")" || exit 1
mkdir -p ~/Desktop/ArduinoQ
APP="$(pwd)/led/app"
{
  date
  echo "=============================================="
  echo " OVERHEARD LED SKETCH - USB INSTALL (manual)"
  echo "=============================================="
  if [ -f "$APP/sketch/sketch.ino" ] && [ -f "$APP/python/main.py" ] && [ -f "$APP/app.yaml" ]; then echo "App folder OK: $APP"; else echo "PROBLEM: app files missing in $APP"; fi
  echo
  BOARD="arduino@100.69.41.76"
  if T="$(ssh -o ConnectTimeout=8 "$BOARD" 'cat ~/netmon/data/token' 2>/dev/null)" && [ -n "$T" ]; then
    (umask 077; printf %s "$T" > "$APP/python/token.txt"); echo "Access key written to led/app/python/token.txt (the app needs it)."
  else
    echo "PROBLEM: could not read the access key from $BOARD. The LED will not follow the dashboard until python/token.txt holds it."
  fi
  echo "1. Plug the UNO Q into this Mac with a USB-C cable (data cable)."
  echo "2. Open Arduino App Lab and select the UNO Q board."
  echo "3. Open or import this folder (a Finder window opens on it now):"
  echo "   $APP"
  echo "4. Press Run in App Lab (it compiles the sketch and uploads it)."
  echo "5. Success: the LED matrix shows the animated character."
  echo "6. Pick matrix/stars/fish/ants/meteor in the Overheard dashboard, LED button."
  echo "If compile fails: copy the error text into ~/Desktop/ArduinoQ/last-led-install.txt and tell Claude."
  echo "Steps 2-4 are UNVERIFIED on hardware."
} | tee ~/Desktop/ArduinoQ/last-led-install.txt
open "$APP"
echo
echo "Saved to ~/Desktop/ArduinoQ/last-led-install.txt"
read -r -p "Press Return to close. "
