"""Handoffs: the ONE file schema every agent uses to pass information (docs/handoff-schema.md).

    HANDOFF__<to-dept>.<to-role|any>__<kind>__<job-id>__<seq>.md        e.g. HANDOFF__research.analyst__assignment__job-004__002.md
The name alone says what the file is for and who should use it, so `list_for` filters by name and never opens a body.
Files are delivered to the recipient department's inbox (departments/<dept>/inbox/); `to: all` goes to handoffs/.
Finished files move to handoffs/archive/{done,superseded,expired}/. Every operation is appended to an audit log.
"""
import json
import math
import os
import re
import tempfile
import time
from collections import deque
from datetime import datetime, timezone

from . import returns
from .loader import COMMAND, SHARED

SCHEMA_VERSION = 1
KINDS = ("assignment", "report", "question", "answer", "data", "decision", "escalation", "returns")
PRIORITIES = ("low", "normal", "high", "urgent")
KEYS = ("schema_version", "id", "title", "from", "to", "kind", "job", "created", "priority", "expires", "supersedes", "token_estimate", "summary")
SECTIONS = ("Context", "Content", "Needed from you", "Attachments")
CROSS_DEPT_KINDS = ("data", "question", "answer")
MAX_BODY, MAX_SUMMARY_LINES, MAX_LINE = 64 * 1024, 3, 160
TOK = r"[a-z0-9][a-z0-9-]*"
NAME_RE = re.compile(r"^HANDOFF__(%s)\.(%s)__(%s)__(%s)__(\d{3,6})\.md$" % (TOK, TOK, "|".join(KINDS), TOK))
FROM_RE = re.compile(r"^(%s)\.(%s)\.([a-z][a-z0-9_-]*)$" % (TOK, TOK))
TO_RE = re.compile(r"^(all|(%s)\.(%s))$" % (TOK, TOK))
ID_RE = re.compile(r"^(%s)-(\d{3,6})$" % TOK)
TIME = "%Y-%m-%dT%H:%M:%SZ"
REASONS = ("done", "superseded", "expired")


class HandoffError(ValueError):
    """A handoff, a name or a handoff operation broke the schema or the routing rules."""


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime(TIME)


def parse_iso(s):
    return datetime.strptime(s, TIME).replace(tzinfo=timezone.utc).timestamp()


def make_name(to, kind, job, seq):
    to = "all.any" if to == "all" else to
    return "HANDOFF__%s__%s__%s__%03d.md" % (to, kind, job, seq)


def parse_name(name):
    """-> {to_dept, to_role, kind, job, seq, tag, to}; raises HandoffError. Looks at the name only."""
    m = NAME_RE.match(name or "")
    if not m:
        raise HandoffError("%r is not a handoff file name (HANDOFF__<dept>.<role|any>__<kind>__<job>__<seq>.md)" % (name,))
    d, r, kind, job, seq = m.groups()
    return {"to_dept": d, "to_role": r, "kind": kind, "job": job, "seq": int(seq), "seq_s": seq, "tag": name[len("HANDOFF__"):-3], "to": "all" if d == "all" else "%s.%s" % (d, r)}


class Handoff:
    def __init__(self, name, meta, sections, text):
        self.name, self.meta, self.sections, self.text = name, meta, sections, text
        self.tag = parse_name(name)["tag"] if name else None

    def __getitem__(self, k):
        return self.meta[k]


def render(meta, sections):
    lines = ["# HANDOFF", "TAG: " + parse_name(make_name(meta["to"], meta["kind"], meta["job"], int(ID_RE.match(meta["id"]).group(2))))["tag"], "---"]
    for k in KEYS:
        if k == "summary":
            lines.append("summary: |")
            lines += ["  " + s for s in meta["summary"]]
        else:
            lines.append("%s: %s" % (k, meta[k]))
    lines.append("---")
    for s in SECTIONS:
        lines += ["## " + s, sections[s].strip() or "none", ""]
    return "\n".join(lines)


def validate(text, name=None, org=None):
    """Strict check of one handoff (same schema for every handoff; unknown keys rejected). With `name`, the file name must agree with the
    content; with `org`, from/to must name real agents and roles. Returns a Handoff or raises HandoffError."""
    if not isinstance(text, str) or len(text.encode()) > MAX_BODY:
        raise HandoffError("handoff must be text under %d KB" % (MAX_BODY // 1024))
    L = text.split("\n")
    if len(L) < 6 or L[0] != "# HANDOFF" or not L[1].startswith("TAG: ") or L[2] != "---":
        raise HandoffError("first lines must be '# HANDOFF', 'TAG: <tag>', '---'")
    try:
        end = L.index("---", 3)
    except ValueError:
        raise HandoffError("front matter is not closed with '---'") from None
    meta, i, fm = {}, 0, L[3:end]
    while i < len(fm):
        k, sep, v = fm[i].partition(":")
        v = v.strip()
        if not sep or k != k.strip() or not k:
            raise HandoffError("front matter line %r: expected 'key: value'" % fm[i])
        if k in meta:
            raise HandoffError("duplicate key %r" % k)
        if k == "summary":
            if v != "|":
                raise HandoffError("summary must be written as 'summary: |' followed by 1-3 indented lines")
            j, vals = i + 1, []
            while j < len(fm) and fm[j].startswith("  "):
                vals.append(fm[j][2:].strip())
                j += 1
            meta[k], i = vals, j
            continue
        meta[k], i = v, i + 1
    unknown = [k for k in meta if k not in KEYS]
    if unknown:
        raise HandoffError("unknown key(s): %s" % ", ".join(unknown))
    if list(meta) != list(KEYS):
        missing = [k for k in KEYS if k not in meta]
        raise HandoffError("front matter must contain exactly these keys in this order: %s%s" % (", ".join(KEYS), "; missing " + ", ".join(missing) if missing else ""))
    if meta["schema_version"] != str(SCHEMA_VERSION):
        raise HandoffError("schema_version must be %d" % SCHEMA_VERSION)
    meta["schema_version"] = SCHEMA_VERSION
    if not meta["title"] or len(meta["title"]) > 120:
        raise HandoffError("title must be 1-120 characters")
    m = ID_RE.match(meta["id"])
    if not m or m.group(1) != meta["job"]:
        raise HandoffError("id must be '<job>-<seq>' (e.g. job-004-002) and match job")
    if not re.match("^%s$" % TOK, meta["job"]):
        raise HandoffError("job must be lowercase letters, digits and '-'")
    f = FROM_RE.match(meta["from"])
    if not f:
        raise HandoffError("from must be '<dept>.<role>.<agent>'")
    if not TO_RE.match(meta["to"]):
        raise HandoffError("to must be '<dept>.<role>', '<dept>.any' or 'all'")
    if meta["kind"] not in KINDS:
        raise HandoffError("kind must be one of %s" % ", ".join(KINDS))
    if meta["priority"] not in PRIORITIES:
        raise HandoffError("priority must be one of %s" % ", ".join(PRIORITIES))
    try:
        created = parse_iso(meta["created"])
        exp = None if meta["expires"] == "none" else parse_iso(meta["expires"])
    except ValueError:
        raise HandoffError("created/expires must look like 2026-01-31T12:00:00Z (expires may be 'none')") from None
    if exp is not None and exp <= created:
        raise HandoffError("expires must be after created")
    if meta["supersedes"] != "none" and not ID_RE.match(meta["supersedes"]):
        raise HandoffError("supersedes must be 'none' or a handoff id")
    if not meta["token_estimate"].isdigit():
        raise HandoffError("token_estimate must be a non-negative integer")
    meta["token_estimate"] = int(meta["token_estimate"])
    if not 1 <= len(meta["summary"]) <= MAX_SUMMARY_LINES or any(not s or len(s) > MAX_LINE for s in meta["summary"]):
        raise HandoffError("summary must be 1-%d non-empty lines of at most %d characters" % (MAX_SUMMARY_LINES, MAX_LINE))
    sections, cur, buf = {}, None, []
    for ln in L[end + 1:]:
        if ln.startswith("## "):
            if cur:
                sections[cur] = "\n".join(buf).strip()
            cur, buf = ln[3:].strip(), []
            if cur in sections:
                raise HandoffError("duplicate section %r" % cur)
        elif cur is None:
            if ln.strip():
                raise HandoffError("text before the first section")
        else:
            buf.append(ln)
    if cur:
        sections[cur] = "\n".join(buf).strip()
    if list(sections) != list(SECTIONS):
        raise HandoffError("body sections must be exactly, in order: %s" % " / ".join(SECTIONS))
    if any(not v for v in sections.values()):
        raise HandoffError("a section is empty (write 'none')")
    for a in sections["Attachments"].split("\n"):
        p = a[2:].strip() if a.startswith("- ") else None
        if not p or (p != "none" and (p.startswith("/") or ".." in p.split("/"))):
            raise HandoffError("Attachments lines must be '- <relative path>' or '- none'")
    if meta["kind"] == "returns":
        try:
            returns.validate(sections["Content"], f.group(1), meta["job"])
        except returns.ReturnsError as e:
            raise HandoffError(str(e)) from None
    tag = L[1][5:]
    want = parse_name(make_name(meta["to"], meta["kind"], meta["job"], int(m.group(2))))
    if tag != want["tag"]:
        raise HandoffError("TAG line %r does not match the front matter (expected %r)" % (tag, want["tag"]))
    if name is not None and parse_name(name)["tag"] != tag:
        raise HandoffError("file name does not match the TAG line")
    if org is not None:
        a = org.agents.get(f.group(3))
        if not a or a.address != meta["from"]:
            raise HandoffError("from %r is not an agent of this organisation" % meta["from"])
        if meta["to"] != "all":
            d, r = meta["to"].split(".")
            if d != COMMAND and d not in org.depts or (r != "any" and (d, r) not in org.by_role):
                raise HandoffError("to %r names no such department/role" % meta["to"])
    return Handoff(name or make_name(meta["to"], meta["kind"], meta["job"], int(m.group(2))), meta, sections, text)


class HandoffStore:
    """Files on disk (a real project, or a temp dir in the simulator). Agents are identified by agent id."""

    def __init__(self, org, departments_dir, handoffs_dir, clock=None, audit_path=None, max_archive=None):
        self.org, self.dd, self.hd, self.clock, self.audit_path, self.max_archive = org, departments_dir, handoffs_dir, clock or time.time, audit_path, max_archive
        self.idx, self.audit_tail, self._arch = {}, deque(maxlen=300), deque()
        self.reads = 0
        self._rescan()

    # ---- layout
    def inbox(self, dept):
        return self.hd if dept == "all" else os.path.join(self.dd, SHARED if dept == COMMAND else dept, "inbox")

    def _dirs(self):
        return [self.hd] + [self.inbox(d) for d in self.org.depts]

    def _rescan(self):
        """Rebuild the in-memory index from disk (the store opens its own files; agents never do this)."""
        for d in self._dirs():
            for n in sorted(os.listdir(d)) if os.path.isdir(d) else ():
                if NAME_RE.match(n):
                    h = validate(self._load(os.path.join(d, n)), n)
                    self.idx[n] = self._info(h, os.path.join(d, n))
        for r in REASONS:
            d = os.path.join(self.hd, "archive", r)
            if os.path.isdir(d):
                self._arch.extend(sorted((os.path.join(d, n) for n in os.listdir(d)), key=lambda p: (os.stat(p).st_mtime_ns, p)))

    @staticmethod
    def _load(path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def _info(h, path):
        return {"path": path, "frm": h["from"].split(".")[2], "to": h["to"], "id": h["id"], "expires": None if h["expires"] == "none" else parse_iso(h["expires"])}

    def _audit(self, action, actor, name, ok=True, reason=""):
        rec = {"ts": round(self.clock(), 3), "action": action, "actor": actor, "name": name, "ok": ok}
        if reason:
            rec["reason"] = reason
        self.audit_tail.append(rec)
        if self.audit_path:
            os.makedirs(os.path.dirname(os.path.abspath(self.audit_path)), exist_ok=True)
            if os.path.exists(self.audit_path) and os.path.getsize(self.audit_path) > 1 << 20:
                os.replace(self.audit_path, self.audit_path + ".1")
            with open(self.audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")

    # ---- routing (names only)
    def _addressed(self, p, agent):
        return p["to_dept"] == "all" or (p["to_dept"] == agent.dept and p["to_role"] in (agent.role, "any"))

    def _agent(self, aid):
        if aid not in self.org.agents:
            raise HandoffError("unknown agent %r" % (aid,))
        return self.org.agents[aid]

    def list_for(self, agent_id, kinds=None, job=None):
        """File names addressed to this agent (its department's inbox plus broadcasts), by NAME ONLY: bodies are never opened.
        -> [{name, tag, kind, job, seq, to}] sorted by (job, seq). Expired handoffs are archived first."""
        a = self._agent(agent_id)
        self.sweep()
        out = []
        for d in {self.hd, self.inbox(a.dept)}:
            for n in os.listdir(d) if os.path.isdir(d) else ():
                if not n.startswith("HANDOFF__") or not NAME_RE.match(n):
                    continue
                p = parse_name(n)
                if self._addressed(p, a) and (kinds is None or p["kind"] in kinds) and (job is None or p["job"] == job):
                    out.append({"name": n, "tag": p["tag"], "kind": p["kind"], "job": p["job"], "seq": p["seq"], "to": p["to"]})
        return sorted(out, key=lambda x: (x["job"], x["seq"]))

    def read(self, agent_id, name):
        """Open one handoff. Allowed for an addressee (by name) or the sender; anything else is refused without opening the file."""
        a = self._agent(agent_id)
        p = parse_name(name)
        info = self.idx.get(name)
        if not (self._addressed(p, a) or (info and info["frm"] == agent_id)):
            self._audit("read", agent_id, name, False, "not addressed to this agent")
            raise HandoffError("%s may not read %s: not addressed to %s.%s" % (agent_id, name, a.dept, a.role))
        path = info["path"] if info else next((os.path.join(self.hd, "archive", r, name) for r in REASONS if os.path.exists(os.path.join(self.hd, "archive", r, name))), None)
        if not path or not os.path.exists(path):
            raise HandoffError("no such handoff %s" % name)
        h = validate(self._load(path), name, self.org)
        self.reads += 1
        self._audit("read", agent_id, name)
        return h

    def mark_done(self, agent_id, name):
        a = self._agent(agent_id)
        p = parse_name(name)
        info = self.idx.get(name)
        if not info:
            raise HandoffError("%s is not an active handoff" % name)
        ok = (info["frm"] == agent_id or a.id == self.org.root) if p["to_dept"] == "all" else self._addressed(p, a)
        if not ok:
            self._audit("done", agent_id, name, False, "not addressed to this agent")
            raise HandoffError("%s may not close %s" % (agent_id, name))
        self._archive(name, "done", agent_id)

    def active(self):
        return sorted(self.idx)

    def archived(self, reason=None):
        out = []
        for r in (reason,) if reason else REASONS:
            d = os.path.join(self.hd, "archive", r)
            out += sorted(os.listdir(d)) if os.path.isdir(d) else []
        return out

    def sweep(self):
        now = self.clock()
        for n, info in list(self.idx.items()):
            if info["expires"] is not None and info["expires"] <= now:
                self._archive(n, "expired", "system")

    def _archive(self, name, reason, actor):
        info = self.idx.pop(name)
        dst = os.path.join(self.hd, "archive", reason)
        os.makedirs(dst, exist_ok=True)
        os.replace(info["path"], os.path.join(dst, name))
        self._arch.append(os.path.join(dst, name))
        self._audit({"done": "done", "superseded": "supersede", "expired": "expire"}[reason], actor, name)
        while self.max_archive is not None and len(self._arch) > self.max_archive:
            try:
                os.remove(self._arch.popleft())
            except OSError:
                pass

    # ---- writing
    def _next_seq(self, job):
        top = 0
        for d in self._dirs() + [os.path.join(self.hd, "archive", r) for r in REASONS]:
            for n in os.listdir(d) if os.path.isdir(d) else ():
                if NAME_RE.match(n):
                    p = parse_name(n)
                    if p["job"] == job:
                        top = max(top, p["seq"])
        return top + 1

    def _route_check(self, s, to, kind):
        """Chain-of-command rules. Cross-department traffic is worker -> own lead -> other lead -> worker, and only Leads cross."""
        org = self.org
        if to == "all":
            if s.dept != COMMAND:
                raise HandoffError("only command (Head, General) may broadcast to all")
            return
        d, r = to.split(".")
        if d == s.dept:
            return
        lead = org.leads.get(s.dept)
        if s.dept != COMMAND and s.id != lead:
            raise HandoffError("%s is a worker: it may only address its own department; ask your Lead (%s) to send it" % (s.id, lead))
        if d == COMMAND:
            return                                                              # a Lead reports up
        target = org.agents[org.leads[d]]
        if r != target.role:
            raise HandoffError("a handoff entering %s must be addressed to its lead (%s.%s), not %r" % (d, d, target.role, r))
        if s.dept != COMMAND and kind not in CROSS_DEPT_KINDS:
            raise HandoffError("Lead to Lead handoffs between departments are kinds %s, not %r" % (", ".join(CROSS_DEPT_KINDS), kind))

    def write_handoff(self, frm, to, kind, job, title, summary, context="", content="", needed="", attachments=(), priority="normal", ttl_s=None, supersedes=None, token_estimate=None):
        """Create one handoff from agent id `frm`. `to` = '<dept>.<role>', '<dept>.any' or 'all'. `summary` = text or list of <=3 lines.
        `supersedes` = id of an active handoff (same job; yours, or addressed to you) which is archived as superseded. Returns the file name."""
        try:
            return self._write(frm, to, kind, job, title, summary, context, content, needed, attachments, priority, ttl_s, supersedes, token_estimate)
        except HandoffError as e:
            self._audit("write", frm, make_name(to, kind, job, 0) if isinstance(to, str) and TO_RE.match(to) and kind in KINDS and re.match("^%s$" % TOK, str(job)) else "-", False, str(e))
            raise

    def _write(self, frm, to, kind, job, title, summary, context, content, needed, attachments, priority, ttl_s, supersedes, token_estimate):
        s = self._agent(frm)
        if not isinstance(to, str) or not TO_RE.match(to):
            raise HandoffError("to must be '<dept>.<role>', '<dept>.any' or 'all'")
        if kind not in KINDS or not isinstance(job, str) or not re.match("^%s$" % TOK, job):
            raise HandoffError("bad kind or job")
        if to != "all" and to.split(".")[0] not in self.org.depts:
            raise HandoffError("to %r: no such department" % to)
        self._route_check(s, to, kind)
        if kind == "returns":
            if s.id != self.org.leads.get(s.dept) or to.split(".")[0] != COMMAND:
                raise HandoffError("returns are written by a department Lead and go to command")
            if not supersedes and any(i["id"].startswith(job + "-") for i in self.idx.values()):
                raise HandoffError("%s already has a returns (one per Lead per period): supersede it" % job)
        old = None
        if supersedes:
            m = ID_RE.match(supersedes)
            old = next((n for n, i in self.idx.items() if i["id"] == supersedes), None) if m and m.group(1) == job else None
            if not old:
                raise HandoffError("supersedes %r: no active handoff with that id in job %s" % (supersedes, job))
            if self.idx[old]["frm"] != frm and not self._addressed(parse_name(old), s):
                raise HandoffError("%s may only supersede its own handoffs or ones addressed to it" % frm)
        seq, now = self._next_seq(job), self.clock()
        lines = [x.strip() for x in (summary.split("\n") if isinstance(summary, str) else summary)]
        att = ["- " + a for a in attachments] or ["- none"]
        sections = {"Context": context, "Content": content, "Needed from you": needed, "Attachments": "\n".join(att)}
        meta = {"schema_version": SCHEMA_VERSION, "id": "%s-%03d" % (job, seq), "title": " ".join(str(title).split()), "from": s.address, "to": to, "kind": kind, "job": job,
                "created": iso(now), "priority": priority, "expires": iso(now + ttl_s) if ttl_s else "none", "supersedes": supersedes or "none", "token_estimate": 0, "summary": lines}
        text = render(meta, sections)
        meta["token_estimate"] = token_estimate if token_estimate is not None else math.ceil(len(text) / 4)
        text = render(meta, sections)
        name = make_name(to, kind, job, seq)
        validate(text, name, self.org)
        d = self.inbox(to.split(".")[0])
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, os.path.join(d, name))
        self.idx[name] = self._info(validate(text, name), os.path.join(d, name))
        self._audit("write", frm, name)
        if old:
            self._archive(old, "superseded", frm)
        return name
