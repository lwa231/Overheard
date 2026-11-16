"""Instruction store. Everyone reads; only the Head (the root of the org) may write, and every attempt is appended to the audit log."""
import hashlib
import json
import os
import re
import tempfile
import time

from . import loader

PATH_RE = re.compile(r"^(_shared/(roles|tasks)|[a-z0-9][a-z0-9-]*/instructions/(roles|tasks))/[a-z0-9_-]+\.md$")
MAX_CONTENT = 64 * 1024


class Forbidden(PermissionError):
    pass


class Store:
    def __init__(self, cfg, audit_path):
        self.cfg, self.dir, self.audit_path = cfg, cfg.departments_dir, audit_path
        self.org = loader.load_dir(self.dir, cfg)

    def _audit(self, actor, path, action, ok, reason="", content=None):
        rec = {"ts": round(time.time(), 3), "actor": actor, "path": path, "action": action, "ok": ok}
        if reason:
            rec["reason"] = reason
        if content is not None:
            rec["sha256"], rec["bytes"] = hashlib.sha256(content.encode()).hexdigest(), len(content.encode())
        os.makedirs(os.path.dirname(os.path.abspath(self.audit_path)), exist_ok=True)
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

    def write(self, actor, path, content):
        """Create or replace one instruction file. Raises Forbidden (actor is not the root) or ValueError (bad path/content/org)."""
        path = path if isinstance(path, str) else ""
        action = "update" if path in loader.read_dir(self.dir) else "create"
        if actor != self.org.root:
            self._audit(actor, path, action, False, "only the head may edit instructions")
            raise Forbidden("only the head (%s) may edit instructions" % self.org.root)
        try:
            if not PATH_RE.match(path):
                raise ValueError("path must look like _shared/{roles,tasks}/<name>.md or <department>/instructions/{roles,tasks}/<name>.md")
            if not isinstance(content, str) or not content.strip() or len(content.encode()) > MAX_CONTENT:
                raise ValueError("content must be non-empty text under %d KB" % (MAX_CONTENT // 1024))
            files = loader.read_dir(self.dir)
            files[path] = content if content.endswith("\n") else content + "\n"
            org = loader.load_files(files, self.cfg)                # the whole org must still validate, else nothing is written
            if org.root != self.org.root:
                raise ValueError("the head cannot be changed through this API")
        except ValueError as e:
            self._audit(actor, path, action, False, str(e))
            raise
        full = os.path.join(self.dir, *path.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(full))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(files[path])
        os.replace(tmp, full)
        self._audit(actor, path, action, True, content=files[path])
        self.org = org
        return {"ok": True, "path": path, "action": action}

    def read(self, agent_id, path):
        """An agent reads one instruction file; refused (loader.IsolationError) outside its chain, its department and the shared library."""
        if agent_id not in self.org.agents:
            raise KeyError(agent_id)
        try:
            text = self.org.read_instruction(agent_id, path)
        except loader.IsolationError as e:
            self._audit(agent_id, path, "read", False, "cross-department read")
            raise e
        return text

    def audit(self, limit=50):
        try:
            with open(self.audit_path, encoding="utf-8") as f:
                return [json.loads(x) for x in f.read().splitlines()[-limit:]]
        except OSError:
            return []
