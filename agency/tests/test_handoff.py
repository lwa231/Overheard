import builtins
import os

import pytest

from agency import handoff, loader
from agency.handoff import HandoffError, HandoffStore, parse_name, validate


class Clock:
    def __init__(self):
        self.t = 1767225600.0

    def __call__(self):
        return self.t


@pytest.fixture
def org(cfg):
    return loader.load_dir(cfg.departments_dir, cfg)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def hs(org, clock, tmp_path):
    return HandoffStore(org, str(tmp_path / "departments"), str(tmp_path / "handoffs"), clock, str(tmp_path / "audit.log"))


def put(hs, frm="research-lead", to="research.scout", kind="assignment", job="job-001", **kw):
    return hs.write_handoff(frm, to, kind, job, kw.pop("title", "T"), kw.pop("summary", "one line"), "ctx", "content", "needed", **kw)


def good(hs):
    n = put(hs, ttl_s=60, token_estimate=1234)
    return n, hs._load(hs.idx[n]["path"])


def test_roundtrip_and_layout(hs, tmp_path):
    n, text = good(hs)
    assert n == "HANDOFF__research.scout__assignment__job-001__001.md"
    assert os.path.exists(tmp_path / "departments" / "research" / "inbox" / n)               # delivered to the recipient department's inbox
    lines = text.split("\n")
    assert lines[0] == "# HANDOFF" and lines[1] == "TAG: research.scout__assignment__job-001__001"
    h = validate(text, n)
    assert list(h.meta) == list(handoff.KEYS) and h["token_estimate"] == 1234 and h["from"] == "research.lead.research-lead" and list(h.sections) == list(handoff.SECTIONS)
    assert validate(text, n, hs.org).tag == "research.scout__assignment__job-001__001"


def mutate(text, a, b):
    assert a in text
    return text.replace(a, b, 1)


BAD = {
    "unknown key": lambda t: mutate(t, "priority: normal\n", "priority: normal\nmood: good\n"),
    "missing key": lambda t: mutate(t, "priority: normal\n", ""),
    "keys out of order": lambda t: mutate(mutate(t, "kind: assignment\n", ""), "job: job-001\n", "job: job-001\nkind: assignment\n"),
    "schema version": lambda t: mutate(t, "schema_version: 1", "schema_version: 2"),
    "bad kind": lambda t: mutate(mutate(t, "kind: assignment", "kind: gossip"), "__assignment__", "__gossip__"),
    "bad priority": lambda t: mutate(t, "priority: normal", "priority: whenever"),
    "bad from": lambda t: mutate(t, "from: research.lead.research-lead", "from: research-lead"),
    "bad to": lambda t: mutate(t, "to: research.scout", "to: scout"),
    "id mismatch": lambda t: mutate(t, "id: job-001-001", "id: job-002-001"),
    "bad time": lambda t: mutate(t, "created: 2026-01-01T00:00:00Z", "created: yesterday"),
    "expires before created": lambda t: mutate(t, "expires: 2026-01-01T00:01:00Z", "expires: 2025-12-31T00:00:00Z"),
    "tokens not int": lambda t: mutate(t, "token_estimate: 1234", "token_estimate: lots"),
    "summary 4 lines": lambda t: mutate(t, "  one line\n", "  a\n  b\n  c\n  d\n"),
    "summary missing": lambda t: mutate(t, "summary: |\n  one line\n", "summary: |\n"),
    "section missing": lambda t: mutate(t, "## Needed from you\nneeded\n\n", ""),
    "sections reordered": lambda t: mutate(mutate(t, "## Content", "## TMP"), "## Context", "## Content").replace("## TMP", "## Context"),
    "extra section": lambda t: t + "## Extras\nx\n",
    "empty section": lambda t: mutate(t, "needed\n", "\n"),
    "tag mismatch": lambda t: mutate(t, "TAG: research.scout__", "TAG: research.analyst__"),
    "no title line": lambda t: t.split("\n", 1)[1],
    "absolute attachment": lambda t: mutate(t, "- none", "- /etc/passwd"),
    "parent attachment": lambda t: mutate(t, "- none", "- ../x"),
}


@pytest.mark.parametrize("case", BAD)
def test_strict_validator(hs, case):
    n, text = good(hs)
    validate(text, n)
    with pytest.raises(HandoffError):
        validate(BAD[case](text), n)


def test_validator_checks_org_and_name(hs):
    n, text = good(hs)
    with pytest.raises(HandoffError, match="not an agent"):
        validate(mutate(text, "research.lead.research-lead", "research.lead.ghost"), n, hs.org)
    with pytest.raises(HandoffError, match="no such department"):
        validate(mutate(mutate(text, "to: research.scout", "to: nowhere.scout"), "TAG: research.scout", "TAG: nowhere.scout"), None, hs.org)
    with pytest.raises(HandoffError, match="file name"):
        validate(text, "HANDOFF__research.scout__report__job-001__001.md")


@pytest.mark.parametrize("name", ["HANDOFF__research.scout__assignment__job-001__001.md", "HANDOFF__all.any__data__job-9__0007.md"])
def test_names_parse(name):
    assert parse_name(name)["tag"] == name[9:-3]


@pytest.mark.parametrize("name", ["handoff__a.b__report__j__001.md", "HANDOFF__a.b__gossip__j__001.md", "HANDOFF__a__report__j__001.md", "HANDOFF__a.b__report__j__1.md",
                                  "HANDOFF__a_b.c__report__j__001.md", "HANDOFF__a.b__report__j__001.txt", None])
def test_bad_names(name):
    with pytest.raises(HandoffError):
        parse_name(name)


def test_list_for_filters_by_name_only(hs, monkeypatch):
    a = put(hs, to="research.scout")
    b = put(hs, to="research.analyst", job="job-002")
    c = put(hs, to="research.any", kind="data", job="job-003")
    d = put(hs, frm="boss", to="all", kind="decision", job="job-004")
    e = put(hs, frm="general", to="marketing.lead", job="job-005")
    # a body that is garbage: routing must not care, because routing never opens it
    with open(hs.idx[b]["path"], "w") as f:
        f.write("garbage")

    def boom(*a, **k):
        raise AssertionError("list_for opened a file")
    monkeypatch.setattr(HandoffStore, "_load", staticmethod(boom))
    real_open = builtins.open
    monkeypatch.setattr(builtins, "open", boom)
    try:
        scout, analyst, mlead = (hs.list_for(x) for x in ("scout", "analyst", "marketing-lead"))
        kinds = hs.list_for("scout", kinds=("data",))
        job = hs.list_for("scout", job="job-001")
    finally:
        monkeypatch.setattr(builtins, "open", real_open)
    assert [x["name"] for x in scout] == [a, c, d] and [x["name"] for x in analyst] == [b, c, d] and [x["name"] for x in mlead] == [d, e]
    assert [x["name"] for x in kinds] == [c] and [x["name"] for x in job] == [a]
    assert all(set(x) == {"name", "tag", "kind", "job", "seq", "to"} for x in scout) and hs.reads == 0
    assert hs.list_for("fin-lead") == [x for x in hs.list_for("fin-lead") if x["to"] == "all"]      # nobody else's mail, only the broadcast


def test_read_is_for_addressees_only(hs):
    a = put(hs, to="research.scout")
    assert hs.read("scout", a)["to"] == "research.scout" and hs.read("research-lead", a)["from"].endswith("research-lead")    # addressee, and the sender
    for who in ("analyst", "marketing-lead", "copywriter"):
        with pytest.raises(HandoffError, match="not addressed"):
            hs.read(who, a)
    assert any(r["action"] == "read" and not r["ok"] for r in hs.audit_tail)


def test_done_supersede_expire_archive(hs, clock):
    a = put(hs, to="research.scout")
    with pytest.raises(HandoffError):
        hs.mark_done("analyst", a)
    hs.mark_done("scout", a)
    assert hs.archived("done") == [a] and hs.active() == [] and hs.list_for("scout") == []
    q = put(hs, frm="scout", to="research.lead", kind="question", job="job-002")
    ans = put(hs, frm="research-lead", to="research.scout", kind="answer", job="job-002", supersedes="job-002-001")
    assert hs.archived("superseded") == [q] and hs.active() == [ans]
    with pytest.raises(HandoffError, match="supersedes"):
        put(hs, frm="research-lead", to="research.scout", kind="answer", job="job-002", supersedes="job-002-009")
    with pytest.raises(HandoffError, match="supersedes"):
        put(hs, frm="research-lead", to="research.scout", kind="answer", job="job-003", supersedes="job-002-002")   # other job
    with pytest.raises(HandoffError, match="only supersede"):
        put(hs, frm="analyst", to="research.lead", kind="report", job="job-002", supersedes="job-002-002")             # not theirs
    t = put(hs, to="research.scout", job="job-004", ttl_s=30)
    assert t in [x["name"] for x in hs.list_for("scout")]
    clock.t += 31
    assert t not in [x["name"] for x in hs.list_for("scout")] and hs.archived("expired") == [t]


def test_seq_counts_per_job_and_survives_restart(hs, org, clock, tmp_path):
    names = [put(hs, job="job-007") for _ in range(3)]
    assert [parse_name(n)["seq"] for n in names] == [1, 2, 3]
    hs.mark_done("scout", names[0])
    again = HandoffStore(org, hs.dd, hs.hd, clock)
    assert again.active() == names[1:] and put(again, job="job-007").endswith("__004.md")


def test_every_operation_is_audited(hs, tmp_path):
    a = put(hs)
    hs.read("scout", a)
    b = put(hs, frm="scout", to="research.lead", kind="question", job="job-002")
    put(hs, frm="research-lead", to="research.scout", kind="answer", job="job-002", supersedes="job-002-001")
    hs.mark_done("scout", a)
    t = put(hs, job="job-009", ttl_s=1)
    hs.clock = lambda: 1767225600.0 + 99
    hs.sweep()
    with pytest.raises(HandoffError):
        put(hs, frm="scout", to="marketing.lead")
    acts = [(r["action"], r["ok"]) for r in hs.audit_tail]
    assert acts == [("write", True), ("read", True), ("write", True), ("write", True), ("supersede", True), ("done", True), ("write", True), ("expire", True), ("write", False)]
    lines = open(tmp_path / "audit.log").read().splitlines()
    assert len(lines) == len(acts) and b in lines[2] and t in lines[-2]


def test_cross_department_goes_through_leads_only(hs):
    rejected = [
        dict(frm="scout", to="marketing.lead", kind="data"),                     # worker -> other department's lead
        dict(frm="scout", to="marketing.copywriter", kind="data"),               # worker -> other department's worker
        dict(frm="scout", to="command.general", kind="report"),                  # worker -> command, past its own lead
        dict(frm="research-lead", to="marketing.copywriter", kind="data"),       # lead -> other department's worker
        dict(frm="research-lead", to="marketing.any", kind="data"),              # 'any' would reach every worker there
        dict(frm="research-lead", to="marketing.lead", kind="assignment"),       # leads exchange data, they do not give orders
        dict(frm="general", to="research.scout", kind="assignment"),             # command reaches a department through its lead
        dict(frm="boss", to="research.any", kind="assignment"),
        dict(frm="scout", to="all", kind="data"),                                # only command broadcasts
        dict(frm="research-lead", to="all", kind="data"),
    ]
    for kw in rejected:
        with pytest.raises(HandoffError):
            put(hs, **kw)
    assert hs.active() == []
    assert [r["ok"] for r in hs.audit_tail] == [False] * len(rejected)           # every refusal is audited
    # the allowed path: worker -> own lead -> other lead -> worker
    put(hs, frm="scout", to="research.lead", kind="question", job="job-010")
    d = put(hs, frm="research-lead", to="marketing.lead", kind="data", job="job-010")
    put(hs, frm="marketing-lead", to="marketing.copywriter", kind="data", job="job-010")
    put(hs, frm="research-lead", to="command.general", kind="report", job="job-010")
    put(hs, frm="general", to="research.lead", kind="assignment", job="job-010")
    put(hs, frm="boss", to="all", kind="decision", job="job-011")
    assert d in [x["name"] for x in hs.list_for("marketing-lead")] and hs.list_for("copywriter")[0]["kind"] == "data"
    assert d not in [x["name"] for x in hs.list_for("copywriter")] + [x["name"] for x in hs.list_for("scout")]
    with pytest.raises(HandoffError):
        put(hs, frm="ghost", to="research.lead")
    with pytest.raises(HandoffError, match="no such department"):
        put(hs, frm="research-lead", to="nowhere.lead")
