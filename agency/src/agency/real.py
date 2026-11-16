"""TEST MODE: real agents. A job owned by an agent in `test_mode.real_agents` is done by a small local model (net.ask_model): the model gets the agent's role
instruction file, the task text and the owner's latest decision on its earlier outputs. The reply is plain text: stored as a handoff (sim.py) and as a file
<data dir>/outputs/<department>/<job id>.md, and it enters the owner's review queue. Nothing the model writes is executed, posted or sent, and it is never
used as a URL, path or command. The owner's Accept/Reject decisions (+ optional note) are kept in <data dir>/reviews.json."""
import json
import logging
import os
import re

from .gates import Decided, NotFound, save_json

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")           # a department folder name or a file stem: no dots, slashes or spaces
MAX_NOTE, MAX_ROLE, KEEP = 300, 4000, 200
DECISIONS = {"accept": "ACCEPTED", "reject": "REJECTED"}
ITEM_KEYS = {"id", "dept", "job", "agent", "title", "file", "preview", "created", "decision", "note", "decided"}
OPTIONAL = {"secs"}                                      # seconds the model took (older files have none)
FILE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9-]*\.md$")
log = logging.getLogger(__name__)


class ReviewError(ValueError):
    pass


class Real:
    def __init__(self, cfg, model, data_dir, clock):
        """cfg: config.test_mode; model: prompt -> text (net.ask_model bound to the config, or a fake); clock: seconds."""
        self.agents, self.model, self.clock = frozenset(cfg["real_agents"]), model, clock
        self.dir, self.path, self.name, self.error = os.path.join(data_dir, "outputs"), os.path.join(data_dir, "reviews.json"), cfg["model"], ""
        self.items = []
        try:
            with open(self.path, encoding="utf-8") as f:
                items = json.load(f)
            if not isinstance(items, list) or any(not isinstance(i, dict) or not ITEM_KEYS <= set(i) <= ITEM_KEYS | OPTIONAL or not isinstance(i["file"], str)
                                                  or not FILE_RE.match(i["file"]) or i["decision"] not in (None, *DECISIONS) for i in items):
                raise ValueError("unexpected content")
            self.items = items
        except FileNotFoundError:
            pass
        except (OSError, ValueError, RecursionError):
            log.warning("review queue %s unreadable: set aside, starting empty", self.path)
            os.replace(self.path, self.path + ".bad")

    @staticmethod
    def prefix(a):
        """The start of every prompt for agent a: its role file and the fixed rules, and nothing that changes between calls (so a loaded model can reuse it)."""
        return ("You are %s (%s). Your role instructions:\n%s\n\nAnswer in plain text. You have no tools: nothing you write is run, posted or sent anywhere. "
                "Your reply goes to the owner for review.\n\n" % (a.title, a.id, a.body[:MAX_ROLE]))

    def prompt(self, a, task):
        """The model's whole input: the fixed prefix, then the task, then only the owner's latest decision on this agent's outputs (no history)."""
        fb = next((i for i in reversed(self.items) if i["agent"] == a.id and i["decision"]), None)
        note = ". Note: " + fb["note"] if fb and fb["note"] else ""
        return self.prefix(a) + "Task: " + task + ("\n\nOwner feedback on your earlier output: %s (%s): %s%s" % (fb["job"], fb["title"], DECISIONS[fb["decision"]], note) if fb else "")

    def check(self, a, out):
        """out: what the model call returned, or the exception it raised -> the reply text (non-empty). Raises on any failure; the scheduler's finish check turns that into a failed attempt."""
        try:
            if isinstance(out, BaseException):
                raise out
            if not isinstance(out, str) or not out.strip():
                raise ValueError("empty reply")
        except Exception as e:  # noqa: BLE001 - whatever the model client raises is one failed attempt
            self.error = "%s: %s" % (a.id, type(e).__name__)
            raise
        self.error = ""
        return out.strip()

    def save(self, a, job, title, text, secs=0.0):
        """Write the reply to outputs/<department>/<job>.md (the name and folder are checked: they cannot leave the outputs folder) and queue it for review."""
        if not NAME_RE.match(a.dept) or not NAME_RE.match(job):
            raise ValueError("unsafe department or job name")
        d = os.path.join(self.dir, a.dept)
        os.makedirs(d, exist_ok=True)
        stem, n = job, 1
        while os.path.exists(os.path.join(d, stem + ".md")):             # a restarted simulation reuses job ids: never overwrite an earlier output
            n += 1
            stem = "%s-r%d" % (job, n)
        path = os.path.join(d, stem + ".md")
        if not os.path.realpath(path).startswith(os.path.realpath(self.dir) + os.sep):
            raise ValueError("output path leaves the outputs folder")
        with open(path, "x", encoding="utf-8") as f:
            f.write("# %s: %s\nTEST MODE output by %s (%s, model %s). Simulated, nothing was sent anywhere.\n\n%s\n" % (job, title, a.title, a.id, self.name, text))
        lines = [ln.strip()[:160] for ln in text.split("\n") if ln.strip()][:3]
        item = {"id": "%s.%s" % (a.dept, stem), "dept": a.dept, "job": job, "agent": a.id, "title": title[:80], "file": "%s/%s.md" % (a.dept, stem), "preview": lines,
                "created": self.clock(), "decision": None, "note": "", "decided": None, "secs": round(secs, 1)}
        items = self.items + [item]
        gone, self.items = items[:-KEEP], items[-KEEP:]
        save_json(self.path, self.items)
        for i in gone:                                                   # an output that left the queue goes with it (after the queue is saved, so it never points at a missing file)
            try:
                os.remove(os.path.join(self.dir, i["file"]))
            except OSError:
                pass
        return item

    def read(self, rid):
        """The full text of a queued output, found by its id in the queue (the client never supplies a path)."""
        i = next((i for i in self.items if i["id"] == rid), None) if isinstance(rid, str) else None
        if not i:
            raise NotFound("no such output")
        with open(os.path.join(self.dir, i["file"]), encoding="utf-8") as f:
            return f.read()

    def decide(self, d):
        """d = {"id", "decision": accept|reject, "note": optional text}, the body of POST /api/review -> the decided item. NotFound (404) for an unknown id, Decided (409) for a second decision."""
        if (not isinstance(d, dict) or not {"id", "decision"} <= set(d) <= {"id", "decision", "note"} or not isinstance(d["id"], str) or not isinstance(d["decision"], str)
                or d["decision"] not in DECISIONS):
            raise ReviewError('body must be {"id": <output id>, "decision": "accept"|"reject", "note": <optional text>}')
        note = d.get("note", "")
        note = note.strip() if isinstance(note, str) else None
        if note is None or len(note) > MAX_NOTE or not note.isprintable():
            raise ReviewError("note must be at most %d printable characters on one line" % MAX_NOTE)
        i = next((i for i in self.items if i["id"] == d["id"]), None)
        if not i:
            raise NotFound("no such output")
        if i["decision"]:
            raise Decided("output %s is already decided" % i["id"])
        i.update(decision=d["decision"], note=note, decided=self.clock())
        save_json(self.path, self.items)
        return i

    def snapshot(self):
        return {"real_agents": sorted(self.agents), "model": self.name, "error": self.error, "pending": sum(not i["decision"] for i in self.items), "items": self.items[::-1][:10]}

