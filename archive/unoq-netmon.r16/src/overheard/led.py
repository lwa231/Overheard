"""LED matrix control state: which character is shown and how active the network is.

The animation itself runs on the board's MCU (see led/app). This module only decides the
activity level from live stats and remembers the chosen character, served at /api/led.
"""
import json
import os
import threading

from .config import PKG

LEVELS = ("sit", "walk", "run", "sprint")
# summed lookup rate over the last 10 s (excluding the board itself) for each level
THRESHOLDS = (1.0, 6.0, 15.0)


def load_sprites(path=None):
    with open(path or os.path.join(PKG, "sprites.json")) as f:
        return json.load(f)


def level_from_stats(stats):
    rate = sum(d["rate"] for d in stats["devices"] if d["id"] != "this board")
    return sum(rate >= t for t in THRESHOLDS)


class LedState:
    def __init__(self, path, sprites):
        self.path, self.sprites, self.lock = path, sprites, threading.Lock()
        self.character = next(iter(sprites))
        self.brightness = 255
        try:
            with open(path) as f:
                saved = json.load(f)
            if saved.get("character") in sprites:
                self.character = saved["character"]
            self.brightness = int(min(255, max(10, saved.get("brightness", 255))))
        except (OSError, ValueError):
            pass

    def update(self, character=None, brightness=None):
        """Raises KeyError for an unknown character and ValueError for a bad brightness; nothing changes on error."""
        if character is not None and (not isinstance(character, str) or character not in self.sprites):
            raise KeyError(character)
        if brightness is not None and (isinstance(brightness, bool) or not isinstance(brightness, (int, float)) or brightness != brightness):
            raise ValueError("brightness must be a number")
        with self.lock:
            if character is not None:
                self.character = character
            if brightness is not None:
                self.brightness = int(min(255, max(10, brightness)))
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"character": self.character, "brightness": self.brightness}, f)
            os.replace(tmp, self.path)

    def snapshot(self, stats):
        lvl = level_from_stats(stats)
        return {"character": self.character, "brightness": self.brightness, "level": lvl, "level_name": LEVELS[lvl],
                "characters": [{"id": k, "name": v["name"]} for k, v in self.sprites.items()]}
