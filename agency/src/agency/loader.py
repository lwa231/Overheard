"""Build the org tree from instruction files (stdlib only).

departments/_shared/roles/<role>.md          command roles (Head, General): read by everyone through the chain of command
departments/_shared/tasks/<task>.md          shared task library
departments/<dept>/instructions/roles/<role>.md    one file per role; the file stem is the role name used in handoff addresses
departments/<dept>/instructions/tasks/<task>.md    that department's own tasks (visible to its agents only)
departments/<dept>/inbox/                    delivery folder for handoffs addressed to the department (see handoff.py)
Role file front matter:
    id: scout   title: Scout   rank: agent (key from config/agency.json)   reports_to: research-lead (or 'none' for the Head)
    runtime: local (claude-code | local)   tasks: [find-sources, handoff]
Isolation: an agent's effective chain = the command roles above it + its own department. A department's files are never
readable by another department, and an agent can only report to its own department or to command.
"""
import os
import re

from .config import RUNTIMES

ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
DEPT_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")          # no '_' and no '.': departments and roles appear in handoff file names
KEYS = {"id", "title", "rank", "reports_to", "runtime", "tasks"}
SHARED, COMMAND = "_shared", "command"                # folder of the command roles/shared tasks, and the department name those roles carry


class OrgError(ValueError):
    """Something in the instruction files is wrong; the message names the file or agent."""


class IsolationError(PermissionError):
    """An agent tried to read an instruction file outside its own chain, department or the shared library."""


def parse(text, where):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise OrgError("%s: missing front matter (first line must be '---')" % where)
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise OrgError("%s: front matter is not closed with '---'" % where)
    meta = {}
    for ln, raw in enumerate(lines[1:end], 2):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        k, sep, v = s.partition(":")
        k, v = k.strip(), v.strip()
        if not sep or not k:
            raise OrgError("%s:%d: expected 'key: value', got %r" % (where, ln, s))
        if k in meta:
            raise OrgError("%s:%d: duplicate key %r" % (where, ln, k))
        if v.startswith("["):
            if not v.endswith("]"):
                raise OrgError("%s:%d: list for %r is missing ']'" % (where, ln, k))
            meta[k] = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
        else:
            meta[k] = v.strip("'\"")
    return meta, "\n".join(lines[end + 1:]).strip("\n")


class Agent:
    def __init__(self, meta, body, path, cfg, dept, role):
        self.id, self.rank, self.runtime = meta["id"], meta["rank"], meta["runtime"]
        self.title = cfg.titles.get(self.id) or meta["title"]
        self.reports_to = None if meta.get("reports_to", "none") in ("", "none") else meta["reports_to"]
        self.tasks, self.body, self.path = meta.get("tasks", []), body, path
        self.rank_index, self.rank_label = cfg.rank_index[self.rank], cfg.rank_label[self.rank]
        self.dept, self.role = dept, role
        self.children = []

    @property
    def address(self):
        return "%s.%s.%s" % (self.dept, self.role, self.id)


class Task:
    def __init__(self, scope, name, meta, body, path):
        self.scope, self.name, self.title, self.body, self.path = scope, name, meta.get("title") or name, body, path


class Org:
    def __init__(self, cfg, agents, tasks, order, root, files):
        self.cfg, self.agents, self.tasks, self.order, self.root, self.files = cfg, agents, tasks, order, root, files
        self.depts = {}                                      # department -> [agent ids]; 'command' holds Head and General
        for i in order:
            self.depts.setdefault(agents[i].dept, []).append(i)
        self.by_role = {(a.dept, a.role): a.id for a in agents.values()}
        self.leads = {d: next(i for i in ids if agents[agents[i].reports_to].dept == COMMAND) for d, ids in self.depts.items() if d != COMMAND}

    def chain(self, aid):
        """Ancestors first: [head, ..., agent]. Only command roles and the agent's own department can appear (enforced at load)."""
        out = []
        while aid:
            out.append(self.agents[aid])
            aid = self.agents[aid].reports_to
        return out[::-1]

    def effective(self, aid):
        """Effective instructions: every ancestor's own file, top first, then the agent's own."""
        return [{"id": a.id, "title": a.title, "rank": a.rank_label, "path": a.path, "text": a.body} for a in self.chain(aid)]

    def task_for(self, aid, name):
        a = self.agents[aid]
        return self.tasks.get((a.dept, name)) or self.tasks[(SHARED, name)]

    def tasks_of(self, aid):
        return [self.task_for(aid, t) for t in self.agents[aid].tasks]

    def readable(self, aid):
        """Instruction paths (relative to departments/) this agent may read: its chain's role files, the shared task library, its own department's tasks."""
        a = self.agents[aid]
        out = {c.path for c in self.chain(aid)}
        out |= {t.path for (scope, _), t in self.tasks.items() if scope in (SHARED, a.dept)}
        return out

    def read_instruction(self, aid, path):
        if path not in self.readable(aid):
            raise IsolationError("%s (%s) may not read %r: outside its chain, its department and the shared library" % (aid, self.agents[aid].dept, path))
        return self.files[path]

    def signature(self):
        return [(a.id, a.reports_to) for a in self.agents.values()]

    def tree(self, aid=None):
        a = self.agents[aid or self.root]
        return {"id": a.id, "children": [self.tree(c) for c in a.children]}


def read_dir(root):
    """All instruction files as {posix path relative to departments/: text}. Inboxes are not instructions and are skipped."""
    files = {}
    for dp, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d != "inbox"]
        for n in names:
            if n.endswith(".md"):
                p = os.path.join(dp, n)
                with open(p, encoding="utf-8") as f:
                    files[os.path.relpath(p, root).replace(os.sep, "/")] = f.read()
    return files


def load_dir(root, cfg):
    return load_files(read_dir(root), cfg)


def split_path(path):
    """-> (dept, kind 'roles'|'tasks', stem) or None when the path is not a valid instruction location."""
    p = path.split("/")
    if not path.endswith(".md"):
        return None
    if len(p) == 3 and p[0] == SHARED and p[1] in ("roles", "tasks"):
        return COMMAND if p[1] == "roles" else SHARED, p[1], p[2][:-3]
    if len(p) == 4 and p[1] == "instructions" and p[2] in ("roles", "tasks") and p[0] not in (SHARED, COMMAND) and DEPT_RE.match(p[0]):
        return p[0], p[2], p[3][:-3]
    return None


def load_files(files, cfg):
    tasks, agents = {}, {}
    for path in sorted(files):
        loc = split_path(path)
        if loc is None:
            raise OrgError("%s: unexpected file; use departments/<dept>/instructions/{roles,tasks}/<name>.md or %s/{roles,tasks}/<name>.md" % (path, SHARED))
        dept, kind, stem = loc
        if kind == "tasks":
            if not NAME_RE.match(stem):
                raise OrgError("%s: task files are named like 'my-task.md'" % path)
            meta, body = parse(files[path], path) if files[path].lstrip().startswith("---") else ({}, files[path].strip("\n"))
            if set(meta) - {"title"}:
                raise OrgError("%s: task files only take 'title' in front matter" % path)
            tasks[(dept, stem)] = Task(dept, stem, meta, body, path)
        else:
            if not DEPT_RE.match(stem):
                raise OrgError("%s: role file names are lowercase letters, digits and '-' (they appear in handoff names)" % path)
            meta, body = parse(files[path], path)
            bad = set(meta) - KEYS
            if bad:
                raise OrgError("%s: unknown front-matter key(s): %s" % (path, ", ".join(sorted(bad))))
            for k in ("id", "title", "rank", "runtime"):
                if not isinstance(meta.get(k), str) or not meta[k]:
                    raise OrgError("%s: missing %r" % (path, k))
            if not isinstance(meta.get("tasks", []), list) or not isinstance(meta.get("reports_to", ""), str):
                raise OrgError("%s: 'tasks' must be a list like [a, b] and 'reports_to' a single id" % path)
            if not ID_RE.match(meta["id"]):
                raise OrgError("%s: id %r must be lowercase letters, digits, '-' or '_'" % (path, meta["id"]))
            if meta["rank"] not in cfg.rank_index:
                raise OrgError("%s: unknown rank %r (known: %s)" % (path, meta["rank"], ", ".join(cfg.rank_index)))
            if meta["runtime"] not in RUNTIMES:
                raise OrgError("%s: runtime %r must be one of %s" % (path, meta["runtime"], ", ".join(RUNTIMES)))
            if meta["id"] in agents:
                raise OrgError("%s: duplicate agent id %r (also in %s)" % (path, meta["id"], agents[meta["id"]].path))
            agents[meta["id"]] = Agent(meta, body, path, cfg, dept, stem)
    if not agents:
        raise OrgError("no role files found under departments/")
    for (scope, name), t in tasks.items():
        if scope != SHARED and (SHARED, name) in tasks:
            raise OrgError("%s: task %r already exists in the shared library; pick another name" % (t.path, name))
    for a in agents.values():
        if a.reports_to is not None and a.reports_to not in agents:
            raise OrgError("%s: %r reports_to unknown agent %r" % (a.path, a.id, a.reports_to))
        if a.reports_to is not None and a.dept != agents[a.reports_to].dept and agents[a.reports_to].dept != COMMAND:
            raise OrgError("%s: %r (%s) cannot report to %r (%s): reports stay inside the department or go to command"
                           % (a.path, a.id, a.dept, a.reports_to, agents[a.reports_to].dept))
        for t in a.tasks:
            if (a.dept, t) in tasks or (SHARED, t) in tasks:
                continue
            other = sorted(d for (d, n) in tasks if n == t and d != SHARED)
            if other:
                raise OrgError("%s: %r links task %r which belongs to department %s: cross-department instruction reads are not allowed" % (a.path, a.id, t, other[0]))
            raise OrgError("%s: %r links task %r but no such task exists in %s/instructions/tasks or %s/tasks" % (a.path, a.id, t, a.dept, SHARED))
    for a in agents.values():
        seen, cur = [], a
        while cur is not None:
            if cur.id in seen:
                raise OrgError("reporting cycle: %s" % " -> ".join(seen + [cur.id]))
            seen.append(cur.id)
            cur = agents.get(cur.reports_to)
    roots = sorted(a.id for a in agents.values() if a.reports_to is None)
    if len(roots) != 1:
        raise OrgError("need exactly one Head (an agent with no reports_to), found %d%s" % (len(roots), ": " + ", ".join(roots) if roots else ""))
    root = agents[roots[0]]
    if root.rank_index != 0:
        raise OrgError("%s: the Head must have rank %r, not %r" % (root.path, cfg.ranks[0][0], root.rank))
    if root.dept != COMMAND:
        raise OrgError("%s: the Head belongs in %s/roles" % (root.path, SHARED))
    for a in agents.values():
        if a.reports_to is None:
            continue
        p = agents[a.reports_to]
        if a.rank_index <= p.rank_index:
            raise OrgError("%s: %r (%s) cannot report to %r (%s): a report must rank below its superior" % (a.path, a.id, a.rank, p.id, p.rank))
        p.children.append(a.id)
    for a in agents.values():
        a.children.sort()
    for d in sorted({a.dept for a in agents.values()} - {COMMAND}):
        leads = sorted(a.id for a in agents.values() if a.dept == d and agents[a.reports_to].dept == COMMAND)
        if len(leads) != 1:
            raise OrgError("department %r needs exactly one lead (the one agent that reports to command), found %d%s" % (d, len(leads), ": " + ", ".join(leads) if leads else ""))
    for aid in cfg.tiers.overrides:
        if aid not in agents:
            raise OrgError("config/tiers.json: override for unknown agent %r" % aid)
    order = []

    def walk(i):
        order.append(i)
        for c in agents[i].children:
            walk(c)
    walk(root.id)
    return Org(cfg, agents, tasks, order, root.id, dict(files))
