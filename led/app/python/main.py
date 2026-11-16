"""Runs on the UNO Q's Linux side inside Arduino App Lab.
Polls the Overheard agent on the board and forwards the character choice, activity level and
brightness to the sketch over the Router Bridge. Everything it needs is fixed below."""
import json
import os
import time
import urllib.request

from arduino.app_utils import App, Bridge

# The app runs in a container; Overheard runs on the board itself. The board is the container's
# Docker gateway, so this address is fixed. Overheard listens on port 8080.
HOST = "172.17.0.1"
PORT = 8080
URL = "http://%s:%d/api/led" % (HOST, PORT)
# Overheard's access key. "Install LED Sketch.command" writes it to python/token.txt before you import the app.
HERE = os.path.dirname(os.path.abspath(__file__))
try:
    TOKEN = open(os.path.join(HERE, "token.txt")).read().strip()
except OSError:
    TOKEN = os.environ.get("OVERHEARD_TOKEN", "")

last = None
last_msg = None


def say(msg):
    """Print each distinct status once, so App Lab's console shows why nothing is changing."""
    global last_msg
    if msg != last_msg:
        print("overheard-led:", msg, flush=True)
        last_msg = msg


def fetch():
    req = urllib.request.Request(URL, headers={"Cookie": "ov=" + TOKEN})
    return json.load(urllib.request.urlopen(req, timeout=2))


def loop():
    global last
    if not TOKEN:
        say("no access key: python/token.txt is missing or empty. Re-run Install LED Sketch.command")
        time.sleep(5)
        return
    try:
        d = fetch()
        ids = [c["id"] for c in d["characters"]]          # same order as SPRITE_IDS in sprites.h
        state = (ids.index(d["character"]), int(d["level"]), int(d["brightness"]))
    except Exception as e:
        say("cannot read %s (%s: %s)" % (URL, type(e).__name__, e))
        time.sleep(2)
        return
    if state != last:
        Bridge.call("set_state", *state)
        last = state
        say("sent character=%s level=%s brightness=%s" % (d["character"], d["level"], d["brightness"]))
    time.sleep(0.5)


App.run(user_loop=loop)
