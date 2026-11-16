"""Runtime configuration. One immutable object, built once from the command line and passed down."""
import argparse
import ipaddress
import sys
import os
from dataclasses import dataclass

PKG = os.path.dirname(os.path.abspath(__file__))


@dataclass(frozen=True)
class Config:
    port: int = 8080
    host: str = "0.0.0.0"
    dns: bool = False
    dns_port: int = 53
    bind: str = "0.0.0.0"
    upstream: str = "1.1.1.1"
    upstream_port: int = 53        # plain UDP fallback port
    ttl: int = 30
    update_blocklist: bool = False
    no_tls: bool = False
    strict: bool = False
    tls_port: int = 853
    tls_name: str = "cloudflare-dns.com"
    tls_cafile: str | None = None
    upstream2: str = "9.9.9.9"     # second encrypted upstream, tried before plain UDP ("" = none)
    tls_port2: int = 853
    tls_name2: str = "dns.quad9.net"
    expect_ip: str = ""            # board address that should exist at start (logged and waited for, never required)
    demo: bool = False
    data_dir: str = os.path.expanduser("~/.overheard")
    profile_devices: tuple = ()
    profile_all: bool = False
    profiles: bool = True
    no_auth: bool = False
    # Content guard strength. Code-level constants on purpose: there is no flag, setting or API to switch the
    # adult guard or SafeSearch off, or to weaken them.
    penalty_s: int = 90                  # seconds a device stays slowed after its last adult lookup
    penalty_delay: float = 8.0           # seconds added to every lookup from a slowed device
    allow: tuple = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "169.254.0.0/16", "127.0.0.0/8")
    rate: int = 60                 # DNS queries per second allowed per client (burst 2x)
    profile_max_mb: int = 16
    export_profiles: bool = False
    purge_profiles: bool = False

    @property
    def db_path(self):
        return os.path.join(self.data_dir, "profiles.db")


def _ipv4(text):
    """--expect-ip only logs and waits, so a bad value must never stop the service (Restart=always would loop on it): warn, treat as absent."""
    try:
        ipaddress.IPv4Address(text)
    except ValueError:
        if text:
            print("overheard: ignoring --expect-ip %r (not an IPv4 address like 10.10.50.2); starting normally" % text, file=sys.stderr)
        return ""
    return text


def parse(argv=None) -> Config:
    ap = argparse.ArgumentParser(prog="overheard", description=__doc__)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="0.0.0.0", help="address for the dashboard server")
    ap.add_argument("--dns", action="store_true", help="run the DNS listener and ad blocker")
    ap.add_argument("--dns-port", type=int, default=53)
    ap.add_argument("--bind", default="0.0.0.0", help="address for the DNS listener (the board's IP)")
    ap.add_argument("--upstream", default="1.1.1.1")
    ap.add_argument("--upstream-port", type=int, default=53, help="plain DNS port of the upstream (tests)")
    ap.add_argument("--ttl", type=int, default=30, help="cap answer TTL in seconds (0 = off)")
    ap.add_argument("--update-blocklist", action="store_true")
    ap.add_argument("--no-tls", action="store_true", help="send upstream lookups in the clear")
    ap.add_argument("--strict", action="store_true", help="never fall back to plain DNS")
    ap.add_argument("--tls-port", type=int, default=853)
    ap.add_argument("--tls-name", default="cloudflare-dns.com")
    ap.add_argument("--tls-cafile", default=None)
    ap.add_argument("--upstream2", default=None, help="second DoT upstream, tried when the first fails; default 9.9.9.9 only while --upstream is the built-in default; '' disables")
    ap.add_argument("--tls-port2", type=int, default=853)
    ap.add_argument("--tls-name2", default="dns.quad9.net")
    ap.add_argument("--expect-ip", default="", type=_ipv4, help="log a warning (and wait up to 30 s) if the board does not have this IPv4 address at start")
    ap.add_argument("--demo", action="store_true", help="scripted fake traffic")
    ap.add_argument("--data-dir", default=os.path.expanduser("~/.overheard"))
    ap.add_argument("--profile", default="", help="comma separated device IPs to profile (opt-in)")
    ap.add_argument("--profile-all", action="store_true", help="profile every device")
    ap.add_argument("--no-profiles", action="store_true")
    ap.add_argument("--no-auth", action="store_true", help="serve the dashboard without an access key")
    ap.add_argument("--allow", default="", help="comma separated CIDRs allowed to use the DNS server (default: private ranges only)")
    ap.add_argument("--allow-extra", default="", help="comma separated CIDRs added to the default allowed networks")
    ap.add_argument("--rate", type=int, default=60, help="max DNS queries per second per client")
    ap.add_argument("--profile-max-mb", type=int, default=16)
    ap.add_argument("--export-profiles", action="store_true", help="print profile vectors as JSON and exit")
    ap.add_argument("--purge-profiles", action="store_true", help="delete all profile data and exit")
    a = ap.parse_args(argv)
    return Config(port=a.port, host=a.host, dns=a.dns, dns_port=a.dns_port, bind=a.bind,
                  upstream=a.upstream, upstream_port=a.upstream_port, ttl=a.ttl, update_blocklist=a.update_blocklist,
                  no_tls=a.no_tls, strict=a.strict, tls_port=a.tls_port, tls_name=a.tls_name,
                  tls_cafile=a.tls_cafile, upstream2=a.upstream2 if a.upstream2 is not None else (Config.upstream2 if a.upstream == Config.upstream else ""), tls_port2=a.tls_port2, tls_name2=a.tls_name2,
                  expect_ip=a.expect_ip, demo=a.demo, data_dir=a.data_dir,
                  profile_devices=tuple(x.strip() for x in a.profile.split(",") if x.strip()),
                  profile_all=a.profile_all or a.demo, profiles=not a.no_profiles,
                  no_auth=a.no_auth, rate=a.rate,
                  **_allow_kw(a),
                  profile_max_mb=a.profile_max_mb, export_profiles=a.export_profiles,
                  purge_profiles=a.purge_profiles)


def _split(text):
    return tuple(x.strip() for x in text.split(",") if x.strip())


def _allow_kw(a):
    if a.allow:
        return {"allow": _split(a.allow)}
    if a.allow_extra:
        return {"allow": Config.__dataclass_fields__["allow"].default + _split(a.allow_extra)}
    return {}
