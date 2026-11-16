# Install the LED sketch with Arduino App Lab (USB)

App folder (full path):
`/Users/luqman_ahmed/Desktop/ArduinoQ/unoq-netmon.r17/led/app`
(contains `app.yaml`, `sketch/`, `python/`). Double-click `Install LED Sketch.command` to open it in Finder.

1. Plug the UNO Q into the Mac with a USB-C data cable. (UNVERIFIED: whether it needs to be unplugged from other power.)
2. Open Arduino App Lab on the Mac.
3. Select the UNO Q board when App Lab lists it. (UNVERIFIED: exact wording of the board picker.)
4. Open or import the app folder above (App Lab's "open/import app" option; UNVERIFIED which menu item).
5. Press Run. App Lab compiles the sketch and uploads it to the board. (UNVERIFIED on this app.)
6. Success: the 8x13 LED matrix shows the animated character and speeds up with network traffic.
   (The Python side polls the Overheard agent at `/api/led`, so Overheard must be running on the board.)
7. Skins: in the Overheard dashboard click the LED button and choose matrix, stars, fish, ants or meteor.
   They apply on the next poll, no re-upload.

## If the matrix does not follow the dashboard
The app reads Overheard at the fixed address `http://172.17.0.1:8080/api/led` (the board, as seen from App Lab's container) and needs the access key in `led/app/python/token.txt`. `Install LED Sketch.command` writes that file over SSH before you import the app; re-run it and re-import if the console says "no access key". App Lab's console prints one line each time the status changes (`overheard-led: ...`). Send those lines to Claude if it still does not follow.

## If the compile fails
Copy the full error text from App Lab into `~/Desktop/ArduinoQ/last-led-install.txt` and tell Claude.
Do not edit the sketch by hand.

## Not tested
Nothing here has been run on hardware. App Lab steps are from memory, not from docs.
