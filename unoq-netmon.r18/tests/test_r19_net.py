"""r19 network kit: startup bind check, second encrypted upstream, service unit settings, and the board/VPS scripts (fake ssh)."""
import os
import shutil
import socket
import stat
import struct
import subprocess
import sys
import threading

import pytest

from overheard import __main__ as entry
from overheard import config, dnsproto
from overheard import upstream as up
from overheard.upstream import Forwarder

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------- --expect-ip ----------
class Clock:
    def __init__(self):
        self.t = 0.0
        self.slept = 0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s
        self.slept += 1


def test_expect_ip_present_at_once(capsys):
    c = Clock()
    assert entry.check_expected_ip("10.10.50.2", lambda: ["10.10.50.2", "100.64.0.5"], c, c.sleep) is True
    assert c.slept == 0 and "10.10.50.2 is present" in capsys.readouterr().out


def test_expect_ip_appears_late_and_start_continues(capsys):
    c = Clock()
    calls = []

    def lister():
        calls.append(1)
        return ["100.64.0.5"] if len(calls) < 6 else ["100.64.0.5", "10.10.50.2"]
    assert entry.check_expected_ip("10.10.50.2", lister, c, c.sleep) is True
    assert 0 < c.t < 30


def test_expect_ip_never_appears_warns_after_30s_and_does_not_raise(capsys):
    c = Clock()
    assert entry.check_expected_ip("10.10.50.2", lambda: ["192.0.2.9"], c, c.sleep) is False
    assert 30 <= c.t < 32
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and "WARNING" in err and "10.10.50.2" in err and "starting anyway" in err


def test_expect_ip_without_ip_command_skips_the_wait(capsys):
    c = Clock()
    assert entry.check_expected_ip("10.10.50.2", lambda: None, c, c.sleep) is False
    assert c.slept == 0 and "not checking" in capsys.readouterr().out


SAMPLE = ("1: lo    inet 127.0.0.1/8 scope host lo\\       valid_lft forever\n"
          "3: wlan0    inet 10.10.50.2/24 brd 10.10.50.255 scope global dynamic wlan0\\       valid_lft 86000sec\n"
          "5: tailscale0    inet 100.64.0.7/32 scope global tailscale0\\       valid_lft forever\n")


def test_local_ipv4s_parses_ip_output_and_survives_a_missing_ip(monkeypatch):
    monkeypatch.setattr(entry.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, SAMPLE, ""))
    assert entry.local_ipv4s() == ["127.0.0.1", "10.10.50.2", "100.64.0.7"]

    def gone(*a, **k):
        raise FileNotFoundError("ip")
    monkeypatch.setattr(entry.subprocess, "run", gone)
    assert entry.local_ipv4s() is None
    monkeypatch.setattr(entry.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "boom"))
    assert entry.local_ipv4s() is None


def test_new_flags_default_to_todays_behaviour_and_validate():
    c = config.parse([])
    assert c.expect_ip == "" and c.upstream2 == "9.9.9.9" and c.tls_name2 == "dns.quad9.net" and c.tls_port2 == 853
    assert config.parse(["--expect-ip", "10.10.50.2"]).expect_ip == "10.10.50.2"


@pytest.mark.parametrize("bad", ["10.10.50", "not-an-ip", "10.10.50.2/24", "300.1.1.1", "10.10.50.2;reboot", " "])
def test_a_bad_expect_ip_never_stops_the_service(bad, capsys):
    """argparse exiting 2 here would crash-loop the service under Restart=always: a bad value is a warning and counts as absent."""
    assert config.parse(["--expect-ip", bad, "--dns"]).expect_ip == ""
    err = capsys.readouterr().err
    assert err.count(chr(10)) == 1 and "ignoring --expect-ip" in err and "starting normally" in err


def test_second_encrypted_upstream_is_default_only_with_the_default_primary():
    assert config.parse([]).upstream2 == "9.9.9.9"
    assert config.parse(["--upstream", "9.9.9.9"]).upstream2 == ""          # a custom primary: nothing is added silently
    assert config.parse(["--upstream", "8.8.8.8", "--upstream2", "9.9.9.9"]).upstream2 == "9.9.9.9"
    assert len(Forwarder(config.parse(["--upstream", "8.8.8.8"]), {"tls": 0, "plain": 0}).targets) == 1


# ---------- second DoT upstream ----------
def _dot_peer():
    """A fake DoT server on a socketpair (the TLS layer is not what is tested here): answers every framed query."""
    a, b = socket.socketpair()

    def run():
        try:
            while True:
                n = struct.unpack("!H", up._recvn(b, 2))[0]
                q = up._recvn(b, n)
                r = q[:2] + b"\x81\x80" + q[4:]
                b.sendall(struct.pack("!H", len(r)) + r)
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()
    return a


def _udp_echo():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))

    def run():
        while True:
            try:
                pkt, addr = s.recvfrom(4096)
            except OSError:
                return
            s.sendto(pkt[:2] + b"\x81\x82" + pkt[4:], addr)
    threading.Thread(target=run, daemon=True).start()
    return s.getsockname()[1]


def _fwd(monkeypatch, behaviours, argv=()):
    """behaviours[i] is 'ok' or an exception instance for the connect to provider i. Returns (forwarder, connect-log)."""
    log = []
    port = _udp_echo()
    second = [] if "--upstream2" in argv else ["--upstream2", "127.0.0.1"]       # a custom --upstream gets no second provider unless asked
    f = Forwarder(config.parse(["--upstream", "127.0.0.1", "--upstream-port", str(port), *second, *argv]), {"tls": 0, "plain": 0})
    clock = Clock()
    f.clock = clock

    def connect(i=0):
        log.append(i)
        if behaviours[i] == "ok":
            return _dot_peer()
        raise behaviours[i]
    monkeypatch.setattr(f, "_connect", connect)
    return f, log, clock


Q = dnsproto.build_query("ok.org", txid=0x4242)


def test_primary_working_never_touches_the_second_or_plain(monkeypatch):
    f, log, _ = _fwd(monkeypatch, ["ok", "ok"])
    assert f(Q)[:2] == Q[:2] and f(Q)[:2] == Q[:2]
    assert log == [0] and f.counters == {"tls": 2, "plain": 0}      # second query reused the pooled connection


def test_refused_primary_falls_back_to_second_dot_then_skips_primary_for_a_while(monkeypatch):
    f, log, clock = _fwd(monkeypatch, [ConnectionRefusedError("no"), "ok"])
    assert f(Q)[:2] == Q[:2]
    assert log == [0, 1] and f.counters == {"tls": 1, "plain": 0}
    log.clear()
    f.pools[1].get_nowait().close()                  # force a fresh connection to the second provider
    assert f(Q)[:2] == Q[:2] and log == [1]          # primary breaker open: straight to the second
    clock.t += up.DOT_RETRY_S + 1
    log.clear()
    f(Q)
    assert log and log[0] == 0                       # primary tried again after the pause


def test_both_encrypted_upstreams_down_ends_on_plain_udp_and_is_not_retried(monkeypatch):
    f, log, _ = _fwd(monkeypatch, [ConnectionResetError("x"), ConnectionRefusedError("y")])
    assert f(Q)[:2] == Q[:2]
    assert log == [0, 1] and f.counters == {"tls": 0, "plain": 1}
    assert f(Q)[:2] == Q[:2] and log == [0, 1]        # circuit breaker: no new DoT attempts


def test_timeout_means_filtered_port_so_no_second_wait(monkeypatch):
    f, log, _ = _fwd(monkeypatch, [TimeoutError("853 filtered"), "ok"])
    assert f(Q)[:2] == Q[:2]
    assert log == [0] and f.counters == {"tls": 0, "plain": 1}


class _Mute:
    """Accepts the connection and the query, then never answers (what a hung provider looks like)."""
    def settimeout(self, t):
        pass

    def sendall(self, b):
        pass

    def recv(self, n):
        raise TimeoutError("no answer")

    def close(self):
        pass


def test_a_primary_that_accepts_but_never_answers_costs_no_wait_on_the_second(monkeypatch):
    f, log, _ = _fwd(monkeypatch, [None, "ok"])
    monkeypatch.setattr(f, "_connect", lambda i=0: (log.append(i), _Mute())[1])
    assert f(Q)[:2] == Q[:2]
    assert log == [0] and f.counters == {"tls": 0, "plain": 1}            # went to plain UDP, the second provider was not tried
    assert f(Q)[:2] == Q[:2] and log == [0]                                # and both stay skipped for the retry pause


def test_strict_never_falls_back_to_plain(monkeypatch):
    f, log, _ = _fwd(monkeypatch, [ConnectionRefusedError("a"), ConnectionRefusedError("b")], ["--strict"])
    with pytest.raises(ConnectionError):
        f(Q)
    assert log == [0, 1] and f.counters["plain"] == 0


def test_second_provider_can_be_switched_off(monkeypatch):
    f, log, _ = _fwd(monkeypatch, [ConnectionRefusedError("a")], ["--upstream2", ""])
    assert len(f.targets) == 1
    assert f(Q)[:2] == Q[:2] and log == [0] and f.counters["plain"] == 1


def test_second_provider_uses_its_own_address_port_and_certificate_name(monkeypatch):
    seen = {}

    class Ctx:
        def wrap_socket(self, s, server_hostname=None):
            seen["name"] = server_hostname
            return s
    monkeypatch.setattr(up.socket, "create_connection", lambda addr, timeout=None: seen.setdefault("addr", addr) and addr)
    f = Forwarder(config.parse(["--tls-port2", "8853"]), {"tls": 0, "plain": 0})
    f._ctx = Ctx()
    f._connect(1)
    assert seen == {"addr": ("9.9.9.9", 8853), "name": "dns.quad9.net"}


# ---------- service unit ----------
def test_installer_unit_restarts_forever_and_waits_for_the_network():
    sh = open(os.path.join(ROOT, "scripts", "install.sh"), encoding="utf-8").read()
    for line in ("Restart=always", "RestartSec=2", "StartLimitIntervalSec=0", "After=network-online.target", "Wants=network-online.target"):
        assert line in sh
    assert "--expect-ip" in sh and "BOARD_LAN_IP" in sh


# ---------- scripts ----------
NEW_SCRIPTS = ["scripts/net_static.sh", "scripts/vps_check.sh", "Set Board Address.command", "Check VPS.command"]


@pytest.mark.parametrize("name", NEW_SCRIPTS)
def test_new_scripts_are_valid_bash(name):
    assert subprocess.run(["bash", "-n", os.path.join(ROOT, name)]).returncode == 0
    text = open(os.path.join(ROOT, name), encoding="utf-8").read()
    assert text.startswith("#!/usr/bin/env bash")


@pytest.mark.skipif(sys.platform == "win32", reason="exec bit is not tracked on Windows")
@pytest.mark.parametrize("name", NEW_SCRIPTS)
def test_new_scripts_are_executable(name):
    assert os.stat(os.path.join(ROOT, name)).st_mode & stat.S_IXUSR


def test_vps_conf_is_ignored_and_the_example_holds_no_real_values():
    assert "vps.conf" in open(os.path.join(ROOT, ".gitignore")).read().split()
    ex = open(os.path.join(ROOT, "vps.conf.example")).read()
    assert "CHANGE-ME" in ex and ex.count("CHANGE-ME") == 2
    home = open(os.path.join(ROOT, "sites", "home.conf.example")).read()
    assert "#BOARD_LAN_IP=" in home and "\nBOARD_LAN_IP=" not in home
    assert "BOARD_LAN_IP" not in open(os.path.join(ROOT, "sites", "apartment.conf")).read()


FAKE_SSH = r'''#!/bin/sh
# logs every call; the apply session (ssh -t) and the confirm check can be given exit codes
echo "$*" >> "$FAKE_SSH_LOG"
case " $* " in *" -t "*) exit "${FAKE_APPLY_RC:-0}";; esac
in=$(cat)
case "$in" in
  *netrevert.armed*) printf '%s\n' "$in" >> "$FAKE_SSH_LOG"; exit "${FAKE_CONFIRM_RC:-0}";;
  *) printf '%s\n' "$FAKE_SSH_OUT";;
esac
'''


def _bash(args, env_extra, tmp_path, fake_out=None, stdin="\n"):
    """Run bash with a fake ssh/tailscale/python3/nc/curl/dig first on PATH, so no board, VPS or tailnet is touched."""
    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    (bindir / "ssh").write_text(FAKE_SSH)
    (bindir / "tailscale").write_text("#!/bin/sh\necho '{}'\n")
    (bindir / "python3").write_text('#!/bin/sh\nexec "%s" "$@"\n' % sys.executable.replace("\\", "/"))
    for quiet in ("nc", "dig", "ping"):
        (bindir / quiet).write_text("#!/bin/sh\nexit 0\n")
    (bindir / "curl").write_text("#!/bin/sh\nexit 22\n")
    for f in bindir.iterdir():
        f.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("BOARD", "SITE", "VPS", "FAKE", "NET_STATIC"))}
    env["PATH"] = str(bindir) + os.pathsep + env["PATH"]
    env["FAKE_SSH_OUT"] = fake_out or ""
    env["FAKE_SSH_LOG"] = str(tmp_path / "ssh.log")
    env["NET_STATIC_POLL"] = "0"
    env.update(env_extra)
    return subprocess.run(["bash"] + args, cwd=ROOT, env=env, capture_output=True, text=True, input=stdin, timeout=120)


GOOD_PROBE = ("nm=active\nnetworkd=inactive\nifupdown=no\nsdrun=yes\ndev=wlan0\nuuid=0b9f3a5c-1111-2222-3333-444455556666\ncon=Home\n"
              "ipnow=100.69.41.76/24\ntsip=100.64.0.7\ntsstate=Running\n")
LAN = {"BOARD_LAN_IP": "10.10.50.2/24", "BOARD_LAN_GW": "10.10.50.1"}
TS = {**LAN, "BOARD_HOST": "100.64.0.7"}


def test_net_static_dry_run_prints_the_commands_and_touches_nothing(tmp_path):
    r = _bash(["scripts/net_static.sh", "--dry-run"], LAN, tmp_path)
    assert r.returncode == 0
    assert "ipv4.method manual ipv4.addresses 10.10.50.2/24 ipv4.gateway 10.10.50.1 ipv4.dns 127.0.0.1,9.9.9.9" in r.stdout
    assert "ipv4.method auto" in r.stdout and "--on-active=90" in r.stdout and "nothing is contacted" in r.stdout
    assert "BOARD can still resolve" in r.stdout and not (tmp_path / "ssh.log").exists()


@pytest.mark.parametrize("env,msg", [
    ({}, "BOARD_LAN_IP"),
    ({"BOARD_LAN_IP": "10.10.50.2", "BOARD_LAN_GW": "10.10.50.1"}, "prefix length"),
    ({"BOARD_LAN_IP": "10.10.50/24", "BOARD_LAN_GW": "10.10.50.1"}, "BOARD_LAN_IP must be"),
    ({"BOARD_LAN_IP": "10.10.50.300/24", "BOARD_LAN_GW": "10.10.50.1"}, "BOARD_LAN_IP must be"),
    ({"BOARD_LAN_IP": "10.10.50.0/24", "BOARD_LAN_GW": "10.10.50.1"}, "BOARD_LAN_IP must be"),
    ({"BOARD_LAN_IP": "10.10.50.2/24", "BOARD_LAN_GW": "10.10.50.1; reboot"}, "not an IPv4"),
    ({"BOARD_LAN_IP": "10.10.50.2/40", "BOARD_LAN_GW": "10.10.50.1"}, "BOARD_LAN_IP must be"),
    ({"BOARD_LAN_IP": "10.10.50.2/24", "BOARD_LAN_GW": "10.10.51.1"}, "same subnet"),
    ({"BOARD_LAN_IP": "10.10.50.2/24", "BOARD_LAN_GW": "10.10.50.2"}, "same subnet"),
    ({"BOARD_LAN_IP": "10.10.50.2/24", "BOARD_LAN_GW": "10.10.50.255"}, "same subnet"),
])
def test_net_static_rejects_bad_values_before_contacting_the_board(tmp_path, env, msg):
    r = _bash(["scripts/net_static.sh", "--dry-run"], env, tmp_path)
    assert r.returncode != 0 and msg in r.stdout and not (tmp_path / "ssh.log").exists()


def test_net_static_stops_when_networkmanager_is_not_in_charge(tmp_path):
    out = GOOD_PROBE.replace("nm=active", "nm=inactive").replace("networkd=inactive", "networkd=active")
    r = _bash(["scripts/net_static.sh"], TS, tmp_path, out)
    assert r.returncode != 0 and "STOP: NetworkManager is not running" in r.stdout and "UNVERIFIED" in r.stdout


def test_net_static_refuses_to_run_over_the_lan_address_or_without_tailscale(tmp_path):
    r = _bash(["scripts/net_static.sh"], {**LAN, "BOARD_HOST": "100.69.41.76"}, tmp_path, GOOD_PROBE)
    assert r.returncode != 0 and "Tailscale address is 100.64.0.7" in r.stdout and "BOARD_HOST=100.64.0.7" in r.stdout
    r = _bash(["scripts/net_static.sh"], TS, tmp_path, GOOD_PROBE.replace("tsstate=Running", "tsstate=Stopped"))
    assert r.returncode != 0 and "Tailscale is not running" in r.stdout


def test_net_static_without_systemd_run_changes_nothing_and_says_so(tmp_path):
    r = _bash(["scripts/net_static.sh"], TS, tmp_path, GOOD_PROBE.replace("sdrun=yes", "sdrun=no"))
    assert r.returncode != 0 and "systemd-run is not available" in r.stdout and "Nothing was changed" in r.stdout
    assert " -t " not in (tmp_path / "ssh.log").read_text()                  # never got as far as the sudo session


def test_net_static_apply_confirms_over_a_new_connection_and_keeps_alive(tmp_path):
    r = _bash(["scripts/net_static.sh"], TS, tmp_path, GOOD_PROBE)
    log = (tmp_path / "ssh.log").read_text()
    assert r.returncode == 0 and "OK: the board has 10.10.50.2" in r.stdout and "Confirmed before the deadline" in r.stdout
    assert "-t " in log and "ServerAliveInterval=5" in log.split("-t ", 1)[1].split("\n")[0]          # the apply session notices a dead link
    confirm = [ln for ln in log.splitlines() if "ControlPath=none" in ln]
    assert confirm and "ControlMaster=no" in confirm[0]                                                 # brand-new connection, never a reused one
    for needle in ("getent hosts example.com", "ping -c1 -W2 10.10.50.1", "' 10.10.50.2/'", "netrevert.armed", "u-a < 80", "touch ~/.overheard-net-ok"):
        assert needle in log, needle
    assert log.index("netrevert.armed") < log.index("touch ~/.overheard-net-ok")      # the deadline is checked before the revert is cancelled


def test_net_static_never_prints_ok_when_confirmation_is_late_or_the_session_dies(tmp_path):
    r = _bash(["scripts/net_static.sh"], {**TS, "FAKE_CONFIRM_RC": "3"}, tmp_path, GOOD_PROBE)
    assert r.returncode == 1 and "OK:" not in r.stdout and "NOT confirmed in time" in r.stdout
    r = _bash(["scripts/net_static.sh"], {**TS, "FAKE_CONFIRM_RC": "4"}, tmp_path, GOOD_PROBE)
    assert r.returncode == 1 and "OK:" not in r.stdout and "NOT confirmed" in r.stdout
    r = _bash(["scripts/net_static.sh"], {**TS, "FAKE_APPLY_RC": "3"}, tmp_path, GOOD_PROBE)
    assert r.returncode == 1 and "Nothing was changed on the board" in r.stdout and "OK:" not in r.stdout


def test_lan_checks_accept_good_values_and_reject_the_rest():
    def ok(fn, *a):
        return subprocess.run(["bash", "-c", '. scripts/lan.sh; ' + fn + ' "$@"', "x", *a], cwd=ROOT).returncode == 0
    assert ok("lan_cidr_ok", "10.10.50.2/24") and ok("lan_gw_ok", "10.10.50.2/24", "10.10.50.1")
    for bad in ("10.10.50/24", "10.10.50.2", "10.10.50.2/31", "10.10.50.2/7", "10.10.50.0/24", "10.10.50.255/24", "10.10.050.2/24", "a.b.c.d/24", "10.10.50.2/24x", ""):
        assert not ok("lan_cidr_ok", bad), bad
    for gw in ("10.10.51.1", "10.10.50.2", "10.10.50.0", "10.10.50.255", "10.10.50", "10.10.50.1;x"):
        assert not ok("lan_gw_ok", "10.10.50.2/24", gw), gw


def _install(tmp_path, lan_ip):
    """Runs the real scripts/install.sh against the fake ssh and returns (output, the sudo command it would have sent)."""
    r = _bash(["scripts/install.sh"], {"BOARD": "arduino@100.64.0.7", "BOARD_LAN_IP": lan_ip}, tmp_path, "prev=\nmac=10.0.0.5\nfinal=")
    sent = [ln for ln in (tmp_path / "ssh.log").read_text().splitlines() if "ExecStart" in ln]
    return r, sent[0] if sent else ""


@pytest.mark.skipif(not shutil.which("tar"), reason="tar not available")
def test_install_passes_expect_ip_only_when_the_value_is_valid(tmp_path):
    r, sent = _install(tmp_path, "10.10.50.2/24")
    assert "--expect-ip 10.10.50.2 " in sent + " " and "WARNING" not in r.stdout
    for n, bad in enumerate(("10.10.50/24", "10.10.50.2", "evil;reboot/24", "10.10.50.2/99")):
        r, sent = _install(tmp_path / ("bad%d" % n), bad)
        assert sent and "--expect-ip" not in sent, bad                    # the service must still be installed, and must not get a flag it could choke on
        assert "WARNING: BOARD_LAN_IP=" in r.stdout and "WITHOUT --expect-ip" in r.stdout


def test_vps_check_reports_failures_with_fixes_and_hides_public_addresses(tmp_path):
    conf = tmp_path / "vps.conf"
    conf.write_text("VPS_USER=ops\nVPS_HOST=vps.example.test\n")
    probe = ("R root=yes\nR fwd4=0\nR fwd6=0\nR accept_ra=1\nR ts_state=Running\nR ts_version=1.80.0\nR exit_approved=False\nR advertised=0.0.0.0/0,::/0\n"
             "R wan=eth0\nR wan_mtu=1300\nR ts_mtu=1280\nR v4_uplink=yes\nR v6_uplink=no\nR reboot=yes\nR ufw=active\nR ufw_fwd_policy=DROP\n"
             "R ts_masq=0\nR docker_published=2\nR docker_user_rules=0\nR docker_iptables_off=0\nR gro=off\nR udp=true\nR derp=Test\n"
             "R ts_health=Tailscale is logged in as someone@example.org on box.tail1234.ts.net\n"
             "R peers_direct=0\nR peers_relay=2\nRAW ===== links\nvia 8.8.8.8 dev eth0 src 10.0.0.5 owner someone@example.org host box.tail1234.ts.net\n")
    out = tmp_path / "result.txt"
    r = _bash(["scripts/vps_check.sh"], {"VPS_CONF": str(conf), "OUT": str(out)}, tmp_path, probe)
    assert r.returncode == 0, r.stdout + r.stderr
    text = out.read_text()
    for needle in ("[FAIL] IPv4 forwarding is off", "sudo sysctl -p /etc/sysctl.d/99-tailscale.conf", "Not approved as an exit node",
                   "sudo ethtool -K eth0 rx-udp-gro-forwarding on rx-gro-list off", "Docker publishes 2 port(s)", "needs a reboot",
                   "no working IPv6", "No Tailscale masquerade rule", "only through relays",
                   "stop accepting router advertisements", "net.ipv6.conf.eth0.accept_ra = 2"):
        assert needle in text, needle
    assert text.index("accept_ra = 2") < text.index("net.ipv6.conf.all.forwarding = 1")           # the safe setting comes first
    assert "mtu 1500" not in text and "ip link set" not in text and "No fix is printed on purpose" in text
    assert "8.8.8.8" not in text and "[public-ip]" in text and "10.0.0.5" in text
    assert "someone@example.org" not in text and "tail1234" not in text and "[login]" in text and "[tailnet-name]" in text


def test_vps_check_masquerade_is_tailscales_own_rule_and_lan_text_is_the_right_way_round():
    sh = open(os.path.join(ROOT, "scripts", "vps_check.sh"), encoding="utf-8").read()
    assert "ts-postrouting" in sh and "nat_masq" not in sh and "iptables -t nat -S 2>" not in sh
    assert "devices on the building network can reach this Mac" not in sh and "bypasses the exit node" in sh
    assert "tailscale status 2>&1" not in sh                                    # device names and logins are never collected
