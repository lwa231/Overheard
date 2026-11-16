import os

import pytest

from agency import loader, store
from agency.loader import IsolationError


@pytest.fixture
def org(cfg):
    return loader.load_dir(cfg.departments_dir, cfg)


def test_chain_is_command_plus_own_department(org):
    for aid, a in org.agents.items():
        for c in org.chain(aid):
            assert c.dept in ("command", a.dept)
    assert [c.dept for c in org.chain("scout")] == ["command", "command", "research", "research"]
    assert [c.dept for c in org.chain("copywriter")] == ["command", "command", "marketing", "marketing"]


def test_instruction_reads_are_isolated(org):
    own = "research/instructions/tasks/find-sources.md"
    assert org.read_instruction("scout", own).startswith("---")
    assert org.read_instruction("scout", "research/instructions/roles/lead.md")              # its own chain: the Lead above it
    assert org.read_instruction("scout", "_shared/roles/head.md") and org.read_instruction("scout", "_shared/tasks/handoff.md")
    for who, path in [("scout", "research/instructions/roles/verifier.md"), ("scout", "marketing/instructions/roles/lead.md"), ("scout", "implementation/instructions/roles/builder.md"),
                      ("copywriter", own), ("marketing-lead", own),
                      ("research-lead", "finance-trading/instructions/roles/lead.md"), ("boss", own), ("general", own), ("scout", "../config/agency.json"), ("scout", "nope.md")]:
        with pytest.raises(IsolationError):
            org.read_instruction(who, path)


def test_readable_sets_do_not_overlap_across_departments(org):
    r = {d: set().union(*(org.readable(i) for i in ids)) for d, ids in org.depts.items() if d != "command"}
    shared = {p for p in org.files if p.startswith("_shared/")}
    for d1 in r:
        for d2 in r:
            if d1 != d2:
                assert r[d1] & r[d2] <= shared


def test_store_read_is_audited(cfg, project, tmp_path):
    from agency import config
    st = store.Store(config.load(os.path.join(project, "config", "agency.json")), str(tmp_path / "audit.log"))
    assert st.read("scout", "research/instructions/tasks/find-sources.md")
    with pytest.raises(IsolationError):
        st.read("scout", "marketing/instructions/roles/lead.md")
    with pytest.raises(KeyError):
        st.read("ghost", "x")
    assert [(r["actor"], r["action"], r["ok"]) for r in st.audit()] == [("scout", "read", False)]


def test_api_read_route(project, tmp_path):
    import json

    from agency.__main__ import build
    app = build(project, str(tmp_path / "d"), seed=1, token=None)
    ok = app.route("GET", "/api/instruction?as=scout&path=research/instructions/tasks/find-sources.md")
    assert ok[0] == 200 and "Find sources" in json.loads(ok[2])["text"]
    assert app.route("GET", "/api/instruction?as=scout&path=marketing/instructions/roles/lead.md")[0] == 403
    assert app.route("GET", "/api/instruction?as=nobody&path=x")[0] == 404


def test_writes_must_land_in_valid_places(cfg, project, tmp_path):
    from agency import config
    st = store.Store(config.load(os.path.join(project, "config", "agency.json")), str(tmp_path / "a.log"))
    new = "---\nid: sneak\ntitle: Sneak\nrank: agent\nreports_to: marketing-lead\nruntime: local\ntasks: []\n---\nx"
    with pytest.raises(ValueError, match="reports stay inside"):
        st.write("boss", "research/instructions/roles/sneak.md", new)                  # a research file cannot hang under marketing
    st.write("boss", "marketing/instructions/roles/sneak.md", new)
    assert st.org.agents["sneak"].dept == "marketing"
