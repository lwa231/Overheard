import json
import os

import pytest

from agency import loader, store


@pytest.fixture
def st(cfg, project, tmp_path):
    from agency import config
    c = config.load(os.path.join(project, "config", "agency.json"))
    return store.Store(c, str(tmp_path / "audit.log"))


def test_effective_chain_order(st):
    chain = st.org.effective("scout")
    assert [c["id"] for c in chain] == ["boss", "general", "research-lead", "scout"]
    assert chain[0]["text"].startswith("You are the only point of contact") and chain[-1]["text"].startswith("Find candidate sources")
    assert [c["rank"] for c in chain] == ["Head", "General", "Squad Lead", "Agent"]
    assert [c["id"] for c in st.org.effective("boss")] == ["boss"]


def test_linked_tasks_resolve(st):
    assert st.org.agents["scout"].tasks == ["find-sources", "handoff", "status-update"] and st.org.task_for("scout", "handoff").scope == "_shared"
    assert st.org.task_for("scout", "find-sources").scope == "research"


def test_only_root_may_write(st):
    p = st.dir + "/_shared/tasks/handoff.md"
    before = open(p).read()
    for actor in ("general", "scout", "", None, "BOSS", "nobody"):
        with pytest.raises(store.Forbidden):
            st.write(actor, "_shared/tasks/handoff.md", "---\ntitle: X\n---\nhacked")
    assert open(p).read() == before
    assert st.write("boss", "_shared/tasks/handoff.md", "---\ntitle: Hand-off\n---\nnew words")["action"] == "update"
    assert "new words" in open(p).read() and st.org.task_for("scout", "handoff").body == "new words"


def test_audit_log_records_every_attempt(st):
    with pytest.raises(store.Forbidden):
        st.write("scout", "_shared/tasks/handoff.md", "x")
    st.write("boss", "_shared/tasks/new-one.md", "fresh")
    with pytest.raises(ValueError):
        st.write("boss", "../evil.md", "x")
    recs = [json.loads(x) for x in open(st.audit_path)]
    assert [(r["actor"], r["ok"], r["action"]) for r in recs] == [("scout", False, "update"), ("boss", True, "create"), ("boss", False, "create")]
    assert recs[1]["sha256"] and recs[1]["bytes"] and "only the head" in recs[0]["reason"]
    assert [r["path"] for r in st.audit()] == ["_shared/tasks/handoff.md", "_shared/tasks/new-one.md", "../evil.md"]


@pytest.mark.parametrize("path", ["../x.md", "x/../x.md", "/etc/x.md", "_shared/tasks/a/b.md", "_shared/tasks/x.txt", "org/x", "other/x.md", "_shared/tasks/UP.md",
                                  "command/instructions/roles/x.md", "research/instructions/other/x.md", None])
def test_bad_paths_rejected(st, path):
    with pytest.raises(ValueError):
        st.write("boss", path, "x")


def test_invalid_org_is_not_written(st):
    path = st.dir + "/research/instructions/roles/scout.md"
    before = open(path).read()
    bad = before.replace("reports_to: research-lead", "reports_to: ghost")
    with pytest.raises(loader.OrgError):
        st.write("boss", "research/instructions/roles/scout.md", bad)
    assert open(path).read() == before and st.org.agents["scout"].reports_to == "research-lead"


def test_head_cannot_be_replaced_and_new_role_works(st):
    new = "---\nid: pilot\ntitle: Pilot\nrank: agent\nreports_to: build-lead\nruntime: local\ntasks: [handoff]\n---\nFly."
    st.write("boss", "implementation/instructions/roles/pilot.md", new)
    assert "pilot" in st.org.agents and st.org.agents["pilot"].dept == "implementation" and "pilot" in st.org.agents["build-lead"].children
