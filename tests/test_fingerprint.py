from overheard.fingerprint import identify


def test_windows_pc():
    r = identify(["www.msftconnecttest.com", "ctldl.windowsupdate.com", "x.events.data.microsoft.com"])
    assert r["label"] == "Windows PC" and r["confidence"] == "high"


def test_android_and_mac_and_tv():
    assert identify(["connectivitycheck.gstatic.com", "mtalk.google.com"])["label"] == "Android phone"
    assert identify(["swscan.apple.com", "gsa.apple.com"])["label"] == "Apple device"
    assert identify(["scribe.logs.roku.com", "cloudservices.roku.com"])["label"] == "Roku"


def test_generic_apple_is_not_called_a_mac():
    assert identify(["init.itunes.apple.com", "push.apple.com"])["label"] == "Apple device"


def test_mac_iphone_and_ipad_share_one_label():
    for names in (["swscan.apple.com", "swcdn.apple.com"], ["captive.apple.com", "mesu.apple.com"], ["icloud.com", "mzstatic.com"]):
        assert identify(names)["label"] == "Apple device"
    r = identify(["swscan.apple.com", "swcdn.apple.com"])
    assert r["confidence"] == "high" and not r["shared"]


def test_nintendo_console():
    r = identify(["ctest.cdn.nintendo.net", "atum.hac.lp1.d4c.nintendo.net"])
    assert r["label"] == "Nintendo console" and r["confidence"] == "high"
    assert identify(["ctest.cdn.nintendo.net"])["confidence"] == "medium"
    assert identify(["nintendo.com"])["label"] == "Nintendo console"


def test_names_are_normalised_and_deduplicated():
    r = identify(["SWSCAN.apple.com.", "swscan.apple.com", ""])
    assert r["evidence"] == ["swscan.apple.com"] and r["confidence"] == "medium"


def test_weak_hint_is_low_confidence():
    r = identify(["www.apple.com"])
    assert r["label"] == "Apple device" and r["confidence"] == "low"


def test_shared_address_is_reported_as_several_devices():
    r = identify(["swscan.apple.com", "swcdn.apple.com", "ctldl.windowsupdate.com", "www.msftconnecttest.com",
                  "settings-win.data.microsoft.com"])
    assert r["shared"] and "Windows PC" in r["evidence"]


def test_unknown_and_lookalike_names():
    assert identify(["example.org"])["label"] == "Device"
    assert identify(["notapple.com", "fakewindowsupdate.com"])["label"] == "Device"
