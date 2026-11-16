import pytest

from agency import loader
from agency.loader import OrgError, load_dir, load_files, parse

NOTASK = "---\nid: {id}\ntitle: {id}\nrank: {rank}\nreports_to: {up}\nruntime: local\ntasks: []\n---\nbody {id}\n"


def role(i, rank, up="none", **kw):
    return NOTASK.format(id=i, rank=rank, up=up).replace("runtime: local", "runtime: " + kw.get("runtime", "local"))


def tiny(**over):
    f = {"_shared/roles/head.md": role("h", "head"), "_shared/roles/g.md": role("g", "general", "h"), "d/instructions/roles/l.md": role("l", "squad_lead", "g"),
         "d/instructions/roles/a.md": role("a", "agent", "l"), "_shared/tasks/t.md": "x"}
    f.update(over)
    return {k: v for k, v in f.items() if v is not None}


def test_sample_org(cfg):
    o = load_dir(cfg.departments_dir, cfg)
    ranks = [a.rank for a in o.agents.values()]
    assert o.root == "boss" and len(o.agents) == 20
    assert (ranks.count("head"), ranks.count("general"), ranks.count("squad_lead"), ranks.count("agent")) == (1, 1, 5, 13)
    assert all(2 <= len(o.agents[a].children) <= 4 for a in o.agents if o.agents[a].rank == "squad_lead")
    assert set(o.depts) == {"command", "research", "implementation", "marketing", "operations", "finance-trading"}
    assert len(o.depts["research"]) == 5 and all(len(o.depts[d]) == 3 for d in ("operations", "finance-trading"))
    assert o.agents["scout"].role == "scout" and o.agents["scout"].address == "research.scout.scout"
    assert {a.runtime for a in o.agents.values()} == {"claude-code", "local"}


def test_front_matter_parse():
    meta, body = parse("---\nid: a\ntasks: [x, 'y']\nempty: []\n---\n\nhello\n", "f")
    assert meta == {"id": "a", "tasks": ["x", "y"], "empty": []} and body == "hello"


@pytest.mark.parametrize("text,msg", [("no front matter", "missing front matter"), ("---\nid: a\n", "not closed"), ("---\njunk\n---\n", "key: value"), ("---\ntasks: [a\n---\n", "missing ']'")])
def test_front_matter_errors(text, msg):
    with pytest.raises(OrgError, match=msg):
        parse(text, "f.md")


def test_tiny_ok(cfg):
    assert load_files(tiny(), cfg).chain("a")[0].id == "h"


CASES = {
    "two heads": ({"_shared/roles/x.md": role("x", "head")}, "exactly one Head"),
    "no head": ({"_shared/roles/head.md": None, "_shared/roles/g.md": role("g", "general", "l")}, "exactly one Head|reports_to unknown|cycle|cannot report"),
    "missing superior": ({"d/instructions/roles/a.md": role("a", "agent", "ghost")}, "unknown agent 'ghost'"),
    "cycle": ({"d/instructions/roles/l.md": role("l", "squad_lead", "a"), "d/instructions/roles/a.md": role("a", "agent", "l")}, "reporting cycle"),
    "rank order": ({"d/instructions/roles/a.md": role("a", "agent", "g"), "d/instructions/roles/b.md": role("b", "squad_lead", "a")}, "must rank below"),
    "head not top rank": ({"_shared/roles/head.md": role("h", "general")}, "Head must have rank"),
    "unknown rank": ({"d/instructions/roles/a.md": role("a", "colonel", "l")}, "unknown rank"),
    "bad runtime": ({"d/instructions/roles/a.md": role("a", "agent", "l", runtime="cloud")}, "runtime"),
    "duplicate id": ({"d/instructions/roles/b.md": role("a", "agent", "l")}, "duplicate agent id"),
    "task missing": ({"d/instructions/roles/a.md": role("a", "agent", "l").replace("tasks: []", "tasks: [nope]")}, "no such task exists"),
    "unknown key": ({"d/instructions/roles/a.md": role("a", "agent", "l").replace("tasks: []", "tasks: []\nboss: yes")}, "unknown front-matter"),
    "report across departments": ({"e/instructions/roles/l2.md": role("l2", "squad_lead", "g"), "e/instructions/roles/b.md": role("b", "agent", "l"),
                                 "d/instructions/roles/a.md": role("a", "agent", "l2")}, "reports stay inside the department"),
    "second lead": ({"d/instructions/roles/m.md": role("m", "squad_lead", "g")}, "exactly one lead"),
    "command report below a department": ({"_shared/roles/g.md": role("g", "general", "a")}, "cannot report to"),
    "foreign task": ({"e/instructions/roles/l2.md": role("l2", "squad_lead", "g"), "e/instructions/tasks/secret.md": "x",
                      "d/instructions/roles/a.md": role("a", "agent", "l").replace("tasks: []", "tasks: [secret]")}, "cross-department instruction reads"),
    "task shadows shared": ({"d/instructions/tasks/t.md": "y"}, "already exists in the shared library"),
    "stray file": ({"d/notes.md": "x"}, "unexpected file"),
    "old layout": ({"org/head.md": role("h2", "head")}, "unexpected file"),
    "bad id": ({"d/instructions/roles/a.md": role("A b", "agent", "l")}, "must be lowercase"),
}


@pytest.mark.parametrize("name", CASES)
def test_validation(cfg, name):
    over, msg = CASES[name]
    with pytest.raises(OrgError, match=msg):
        load_files(tiny(**over), cfg)


def test_errors_name_the_file(cfg):
    with pytest.raises(OrgError) as e:
        load_files(tiny(**{"d/instructions/roles/a.md": role("a", "agent", "ghost")}), cfg)
    assert "d/instructions/roles/a.md" in str(e.value)


def test_rank_labels_renameable(cfg):
    cfg.titles["a"] = "Renamed"
    assert load_files(tiny(), cfg).agents["a"].title == "Renamed"
    assert loader.load_files(tiny(), cfg).cfg.rank_label["head"] == "Head"
