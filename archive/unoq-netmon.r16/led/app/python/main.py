"""Runs on the UNO Q's Linux side inside Arduino App Lab.
Polls the Overheard agent (same board, port 8080) and forwards the character choice and network
activity to the sketch over the Router Bridge."""
import json
import time
import urllib.request

from arduino.app_utils import App, Bridge

URL = "http://localhost:8080/api/led"
last = None


def loop():
    global last
    try:
        d = json.load(urllib.request.urlopen(URL, timeout=2))
        ids = [c["id"] for c in d["characters"]]          # same order as SPRITE_IDS in sprites.h
        state = (ids.index(d["character"]), int(d["level"]), int(d["brightness"]))
    except Exception:
        time.sleep(2)
        return
    if state != last:
        Bridge.call("set_state", *state)
        last = state
    time.sleep(1)


App.run(user_loop=loop)
