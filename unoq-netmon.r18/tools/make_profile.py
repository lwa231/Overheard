"""Apple DNS profile helper for Overheard.

Finding (Apple docs): the only DNS payload, com.apple.dnsSettings.managed, accepts
DNSProtocol HTTPS or TLS only -- encrypted DNS, never plain UDP/53. The Wi-Fi payload
(com.apple.wifi.managed) has no DNS keys. The board serves plain DNS, so NO profile can
point an iPhone at it today. By default this tool therefore writes manual steps (no profile).
Only with --dot-host (a name the board will serve DNS-over-TLS on, a future task) does it
write a real .mobileconfig. See docs/auto-dns.md.
"""
import argparse
import os
import plistlib
import sys
import uuid



def _conf_host():
    """The board's address: BOARD_HOST in the environment, else board.conf (and sites/$SITE.conf), else the old default."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    vals = {}
    site = os.environ.get("SITE", "")
    paths = [os.path.join(root, "board.conf")]
    for p in paths + ([os.path.join(root, "sites", site + ".conf")] if site else []):
        try:
            for ln in open(p):
                k, _, v = ln.strip().partition("=")
                if k and not k.startswith("#") and v:
                    vals[k] = v
        except OSError:
            pass
    return os.environ.get("BOARD_HOST") or vals.get("BOARD_HOST") or "100.69.41.76"


BOARD = _conf_host()
ID = "com.overheard.dns"


def manual_steps(board=BOARD):
    return f"""Overheard DNS on iPhone/iPad (manual; Apple profiles cannot set plain DNS)

Why: iOS DNS profiles only support encrypted DNS (DoH/DoT) and the board serves plain DNS.
Wi-Fi profiles carry no DNS setting either. So set it by hand, once per Wi-Fi network:

1. Settings > Wi-Fi > tap the (i) next to your network.
2. Configure DNS > Manual. Delete existing servers, Add Server: {board}. Save.
3. Turn off Settings > [your name] > iCloud > Private Relay (and Limit IP Address Tracking
   on the Wi-Fi network) or the phone may bypass this DNS.

Zero-touch alternative: Tailscale on the phone and board (see docs/auto-dns.md, Lane D).
"""


def build_profile(host, board=BOARD, name="Overheard DNS"):
    """Return a .mobileconfig dict for DNS-over-TLS to `host`, resolving via `board`."""
    dns = {"DNSProtocol": "TLS", "ServerName": host, "ServerAddresses": [board]}
    payload = {
        "PayloadType": "com.apple.dnsSettings.managed", "PayloadIdentifier": f"{ID}.dns",
        "PayloadUUID": str(uuid.uuid4()).upper(), "PayloadVersion": 1,
        "PayloadDisplayName": name, "DNSSettings": dns,
    }
    return {
        "PayloadType": "Configuration", "PayloadIdentifier": ID, "PayloadUUID": str(uuid.uuid4()).upper(),
        "PayloadVersion": 1, "PayloadDisplayName": name, "PayloadDescription": f"Send DNS to Overheard at {board} over TLS.",
        "PayloadOrganization": "Overheard", "PayloadContent": [payload],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--board", default=BOARD, help="board address (default %(default)s)")
    ap.add_argument("--dot-host", help="TLS name the board serves DNS-over-TLS on (not implemented on the board yet)")
    ap.add_argument("--out", default=os.path.expanduser("~/Desktop/ArduinoQ"), help="output folder")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    if not a.dot_host:
        path = os.path.join(a.out, "iPhone-DNS-steps.txt")
        with open(path, "w") as f:
            f.write(manual_steps(a.board))
        print(manual_steps(a.board))
        print(f"No profile written: Apple profiles can't set plain DNS. Steps saved to {path}")
        return 0
    path = os.path.join(a.out, "Overheard-DNS.mobileconfig")
    with open(path, "wb") as f:
        plistlib.dump(build_profile(a.dot_host, a.board), f)
    print(f"Wrote {path}. Needs the board serving DNS-over-TLS on {a.dot_host}:853, else DNS breaks.")
    print("AirDrop it to the device, then Settings > Profile Downloaded > Install.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
