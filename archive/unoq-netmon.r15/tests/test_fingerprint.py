from overheard.fingerprint import identify


def test_windows_pc():
    r = identify(["www.msftconnecttest.com", "ctldl.windowsupdate.com", "x.events.data.microsoft.com"])
    assert r["label"] == "Windows PC" and r["confidence"] == "high"


def test_android_and_mac_and_tv():
    assert identify(["connectivitycheck.gstatic.com", "mtalk.google.com"])["label"] == "Android phone"
    assert identify(["swscan.apple.com", "gsa.apple.com"])["label"] == "Mac"
    assert identify(["scribe.logs.roku.com", "cloudservices.roku.com"])["label"] == "Roku"


def test_generic_apple_is_not_called_a_mac():
    assert identify(["init.itunes.apple.com", "push.apple.com"])["label"] == "Apple device"


def test_shared_address_is_reported_as_several_devices():
    r = identify(["swscan.apple.com", "swcdn.apple.com", "ctldl.windowsupdate.com", "www.msftconnecttest.com",
                  "settings-win.data.microsoft.com"])
    assert r["shared"] and "Windows PC" in r["evidence"]


def test_unknown_and_lookalike_names():
    assert identify(["example.org"])["label"] == "Device"
    assert identify(["notapple.com", "fakewindowsupdate.com"])["label"] == "Device"
