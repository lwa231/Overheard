import calendar
import json

from overheard.profiles import CATEGORIES, ProfileStore, categorize

MON_0900 = calendar.timegm((2026, 11, 2, 9, 30, 0))   # a Monday, 09:30 UTC


def mk(tmp_path, **kw):
    return ProfileStore(str(tmp_path / "p.db"), clock=lambda: MON_0900, **kw)


def test_categorize():
    assert categorize("YouTube", "video", False) == "video"
    assert categorize("TikTok", "feed", False) == "social"
    assert categorize("System", "system", False) is None
    assert categorize("Other", "other", True) == "ads"


def test_counts_land_in_the_right_cell(tmp_path):
    s = mk(tmp_path, everyone=True)
    for _ in range(3):
        s.observe(MON_0900, "10.0.0.2", "YouTube", "video", False)
    s.observe(MON_0900, "10.0.0.2", "Other", "ads", True)
    p = s.profile("10.0.0.2")
    cell = p["week"][0 * 24 + 9]
    assert cell[CATEGORIES.index("video")] == 3 and cell[CATEGORIES.index("ads")] == 1
    assert abs(sum(p["vector"]) - 1) < 1e-3 and p["days_observed"] == 1 and len(p["vector"]) == 168 * len(CATEGORIES)


def test_only_opted_in_devices_are_profiled(tmp_path):
    s = mk(tmp_path, devices=["10.0.0.2"])
    s.observe(MON_0900, "10.0.0.9", "YouTube", "video", False)
    s.observe(MON_0900, "10.0.0.2", "YouTube", "video", False)
    assert [d["id"] for d in s.devices_seen()] == ["10.0.0.2"]


def test_flush_accumulates_and_persists(tmp_path):
    s = mk(tmp_path, everyone=True)
    s.observe(MON_0900, "a", "YouTube", "video", False)
    s.flush()
    s.observe(MON_0900, "a", "YouTube", "video", False)
    s.close()
    s2 = mk(tmp_path, everyone=True)
    assert s2.profile("a")["total"] == 2


def test_daily_rows_are_pruned(tmp_path):
    s = mk(tmp_path, everyone=True)
    s.db.execute("INSERT INTO daily VALUES('a','2000-01-01',0,5)")
    s.observe(MON_0900, "a", "YouTube", "video", False)
    s.flush()
    assert s.db.execute("SELECT COUNT(*) FROM daily WHERE day='2000-01-01'").fetchone()[0] == 0


def test_size_cap_drops_new_counts_instead_of_growing(tmp_path):
    s = mk(tmp_path, everyone=True, max_bytes=64 * 1024)
    for i in range(3000):
        s.observe(MON_0900 + (i % 7) * 86400, "dev%d" % i, "YouTube", "video", False)
    s.flush()
    assert s.size_bytes() <= 64 * 1024 + 8192
    assert s.dropped > 0


def test_export_and_purge(tmp_path):
    s = mk(tmp_path, everyone=True)
    s.observe(MON_0900, "a", "YouTube", "video", False)
    ex = s.export_vectors()
    assert list(ex["devices"]) == ["a"] and json.dumps(ex)
    s.purge()
    assert s.devices_seen() == []


def test_realistic_size(tmp_path):
    """10 devices x 120 days of heavy use must stay far below the cap."""
    s = mk(tmp_path, everyone=True)
    for d in range(10):
        for day in range(120):
            for hour in range(24):
                t = MON_0900 - day * 86400 + hour * 3600
                for ci, cat in enumerate(("YouTube", "TikTok", "Spotify")):
                    s.observe(t, "10.0.0.%d" % d, cat, "video" if ci == 0 else "feed", False)
        s.flush()
    assert s.size_bytes() < 3 << 20
