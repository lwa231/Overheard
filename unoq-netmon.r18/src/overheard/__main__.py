"""Entry point: python3 -m overheard [--dns] [--demo]"""
import errno
import os
import re
import signal
import subprocess
import sys
import threading
import time

from . import auth, config, demo, led as ledmod, peers as peersmod, sampler, sysinfo
from .adult import AdultFilter, FlagLog, Guard, PenaltyBox
from .blocklist import Blocklist
from .dnsserver import DnsServer
from .profiles import ProfileStore, dumps_export
from .server import App, serve
from .settings import Settings
from .state import State
from .upstream import Forwarder


def local_ipv4s():
    """The board's IPv4 addresses from `ip -4 -o addr`; None when `ip` is missing or fails (stdlib only, no netifaces)."""
    try:
        r = subprocess.run(["ip", "-4", "-o", "addr"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return re.findall(r"\binet (\d+\.\d+\.\d+\.\d+)/", r.stdout) if r.returncode == 0 else None


def check_expected_ip(want, lister=local_ipv4s, clock=time.monotonic, sleep=time.sleep, wait_s=30.0):
    """Log the board's addresses and whether `want` is among them. If not, warn and wait up to wait_s for it (Wi-Fi may come up late).
    Never refuses to start: DNS over Tailscale has to survive a LAN problem. Returns True when the address was present."""
    t0 = clock()
    while True:
        have = lister()
        if have is None:
            print("expect-ip: cannot list addresses (no `ip` command); not checking %s" % want, flush=True)
            return False
        if want in have:
            print("expect-ip: %s is present (addresses: %s)" % (want, ", ".join(have)), flush=True)
            return True
        if clock() - t0 >= wait_s:
            break
        sleep(1)
    print("WARNING expect-ip: %s is NOT on this board (addresses: %s); starting anyway on all addresses" % (want, ", ".join(have) or "none"), file=sys.stderr, flush=True)
    return False


def main(argv=None):
    cfg = config.parse(argv)
    store = ProfileStore(cfg.db_path, cfg.profile_max_mb << 20, devices=cfg.profile_devices, everyone=cfg.profile_all) if cfg.profiles or cfg.export_profiles or cfg.purge_profiles else None
    if cfg.export_profiles:
        print(dumps_export(store))
        return 0
    if cfg.purge_profiles:
        store.purge()
        print("profile data deleted")
        return 0
    state = State(settings=Settings(cfg.data_dir))
    if store and cfg.profiles:
        state.listeners.append(store.observe)
        store.start()
    vitals = sysinfo.Vitals()
    threading.Thread(target=sysinfo.sampler, args=(vitals, cfg.demo), daemon=True).start()
    threading.Thread(target=sampler.net_sampler, args=(state, cfg.demo), daemon=True).start()
    if not cfg.demo:
        threading.Thread(target=sampler.conn_poller, args=(state,), daemon=True).start()
    print("loading lists...", flush=True)
    blocklist = Blocklist.load(os.path.join(cfg.data_dir, "blocklist.txt"), cfg.update_blocklist)
    if cfg.demo:
        threading.Thread(target=demo.run, args=(state,), daemon=True).start()
    guard = Guard(AdultFilter.load(cfg.data_dir, cfg.update_blocklist), PenaltyBox(cfg.penalty_s), FlagLog(os.path.join(cfg.data_dir, "flagged.json")))
    def save_flags():
        while True:
            time.sleep(60)
            guard.flags.save()
    threading.Thread(target=save_flags, daemon=True).start()
    print("adult guard: %d listed domains, %ds slowdown after the last adult lookup" % (len(guard.filter), cfg.penalty_s))
    if cfg.expect_ip:
        check_expected_ip(cfg.expect_ip)
    if cfg.dns:
        err = DnsServer(cfg, state, blocklist, Forwarder(cfg, state.dns), guard).start()
        if err:
            print("DNS could not start on %s:%d (%s)." % (cfg.bind, cfg.dns_port, err), file=sys.stderr)
            if getattr(err, "errno", None) == errno.EACCES:
                print("Ports under 1024 need permission. On the board run: sudo sysctl -w net.ipv4.ip_unprivileged_port_start=53", file=sys.stderr)
            elif getattr(err, "errno", None) == errno.EADDRINUSE:
                print("Something else is already using that port. Is Overheard already running (as the service)?", file=sys.stderr)
            return 1
        print("dns: listening on %s:%d, upstream %s" % (cfg.bind, cfg.dns_port, "plain UDP" if cfg.no_tls else "encrypted (DoT)"), flush=True)
    sprites = ledmod.load_sprites()
    peers = peersmod.load(cfg.data_dir)
    if peers:
        print("sites: this board is '%s', peers: %s" % (peers.site, ", ".join(x["name"] for x in peers.summary()["sites"][1:])))
    app = App(cfg, state, store if cfg.profiles else None, ledmod.LedState(os.path.join(cfg.data_dir, "led.json"), sprites), sprites,
              None if cfg.no_auth else auth.load_token(cfg.data_dir), guard, vitals, peers=peers)
    try:
        httpd = serve(app, cfg.host, cfg.port)
    except OSError as e:
        print("Dashboard could not start on port %d (%s). Is Overheard already running?" % (cfg.port, e), file=sys.stderr)
        if store:
            store.close()
        return 1

    def stop(*_):
        threading.Thread(target=httpd.shutdown, daemon=True).start()
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    print("blocklist entries:", len(blocklist))
    print("ready: dashboard on port %d" % cfg.port, flush=True)
    try:
        httpd.serve_forever()
    finally:
        guard.flags.save()
        if store:
            store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
