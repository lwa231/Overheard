"""Settings the owner can change at runtime. Only the slowdown toggle lives here; nothing in this file can touch the adult blocking itself."""
import json
import os
import threading


class Settings:
    def __init__(self, data_dir=None):
        """data_dir=None keeps everything in memory (tests); otherwise changes are saved to <data_dir>/settings.json."""
        self.path = os.path.join(data_dir, "settings.json") if data_dir else None
        self.lock = threading.Lock()
        self._slowdown = False
        try:
            with open(self.path) as f:
                data = json.load(f)
            self._slowdown = isinstance(data, dict) and data.get("slowdown") is True      # anything unreadable or odd means off
        except (OSError, ValueError, TypeError):
            pass

    @property
    def slowdown(self):
        with self.lock:
            return self._slowdown

    @slowdown.setter
    def slowdown(self, value):
        with self.lock:
            self._slowdown = bool(value)
            self._save()

    def _save(self):
        if not self.path:
            return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"slowdown": self._slowdown}, f)
            os.replace(tmp, self.path)
        except OSError as e:
            print("settings not saved: %s" % e, flush=True)
