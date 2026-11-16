"""r16: iPhone profile generator."""
import plistlib
import sys

sys.path.insert(0, "tools")
import make_profile as mp  # noqa: E402


def test_profile_is_valid_plist_with_expected_keys():
    d = plistlib.loads(plistlib.dumps(mp.build_profile("dns.example.ts.net")))
    assert d["PayloadType"] == "Configuration" and d["PayloadVersion"] == 1
    p = d["PayloadContent"][0]
    assert p["PayloadType"] == "com.apple.dnsSettings.managed"
    assert p["DNSSettings"]["DNSProtocol"] == "TLS" and p["DNSSettings"]["ServerName"] == "dns.example.ts.net"


def test_board_address_param():
    assert mp.build_profile("h", board="10.1.2.3")["PayloadContent"][0]["DNSSettings"]["ServerAddresses"] == ["10.1.2.3"]
    assert "10.1.2.3" in mp.manual_steps("10.1.2.3")


def test_uuids_unique():
    a, b = mp.build_profile("h"), mp.build_profile("h")
    ids = {a["PayloadUUID"], a["PayloadContent"][0]["PayloadUUID"], b["PayloadUUID"], b["PayloadContent"][0]["PayloadUUID"]}
    assert len(ids) == 4


def test_default_writes_steps_not_profile(tmp_path):
    assert mp.main(["--out", str(tmp_path)]) == 0
    assert [p.name for p in tmp_path.iterdir()] == ["iPhone-DNS-steps.txt"]


def test_dot_host_writes_profile(tmp_path):
    assert mp.main(["--out", str(tmp_path), "--dot-host", "h.example"]) == 0
    plistlib.loads((tmp_path / "Overheard-DNS.mobileconfig").read_bytes())
