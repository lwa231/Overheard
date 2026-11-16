#!/usr/bin/env python3
"""
Live YouTube traffic analyzer — run this on the board while watching YouTube.
Captures raw TLS ClientHellos from the wire, extracts SNI hostnames,
measures packet sizes, and shows whether our adstream filter would have
caught each flow.

Usage (on the board):
    sudo python3 live_capture.py

No dependencies beyond stdlib + raw socket access (needs root).
"""
import hashlib
import ipaddress
import os
import re
import socket
import struct
import sys
import time
from collections import defaultdict
from typing import Optional

# ── copy of our SNI patterns so this script is self-contained ──────────────
AD_SNI_PATTERNS = (
    re.compile(r"^redirector\.googlevideo\.com$"),
    re.compile(r"^r\d+---sn-[a-z0-9]+-ad[a-z]\w*\.googlevideo\.com$"),
    re.compile(r"^ad[s]?\.youtube\.com$"),
    re.compile(r"pagead\d*\.googlesyndication\.com$"),
    re.compile(r"^adservice\.google\.[a-z.]+$"),
    re.compile(r"^s\.youtube\.com$"),
    re.compile(r"\.doubleclick\.net$"),
)

YOUTUBE_HOSTS = (
    "googlevideo.com",
    "youtube.com",
    "googlesyndication.com",
    "doubleclick.net",
    "googleapis.com",
    "ytimg.com",
    "ggpht.com",
    "googleadservices.com",
)

RESET  = "\033[0m"
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"


def is_youtube(sni: str) -> bool:
    return any(sni == h or sni.endswith("." + h) for h in YOUTUBE_HOSTS)


def sni_is_ad(sni: str) -> bool:
    return any(p.search(sni) for p in AD_SNI_PATTERNS)


def extract_sni(payload: bytes) -> Optional[str]:
    try:
        if len(payload) < 43 or payload[0] != 0x16 or payload[5] != 0x01:
            return None
        pos = 9 + 2 + 32
        sid_len = payload[pos]; pos += 1 + sid_len
        cs_len = struct.unpack_from("!H", payload, pos)[0]; pos += 2 + cs_len
        comp_len = payload[pos]; pos += 1 + comp_len
        if pos + 2 > len(payload):
            return None
        ext_end = pos + 2 + struct.unpack_from("!H", payload, pos)[0]
        pos += 2
        while pos + 4 <= ext_end:
            ext_type = struct.unpack_from("!H", payload, pos)[0]
            ext_len  = struct.unpack_from("!H", payload, pos + 2)[0]
            pos += 4
            if ext_type == 0x0000 and ext_len >= 5:
                name_len = struct.unpack_from("!H", payload, pos + 3)[0]
                return payload[pos + 5: pos + 5 + name_len].decode("ascii", errors="replace").lower()
            pos += ext_len
    except (IndexError, struct.error):
        pass
    return None


def parse_ip_tcp(raw: bytes):
    """Return (src_ip, dst_ip, sport, dport, tcp_payload) or None."""
    try:
        if (raw[0] >> 4) != 4:          # IPv4 only
            return None
        proto = raw[9]
        if proto != 6:                   # TCP only
            return None
        ihl = (raw[0] & 0x0F) * 4
        src = socket.inet_ntoa(raw[12:16])
        dst = socket.inet_ntoa(raw[16:20])
        seg = raw[ihl:]
        if len(seg) < 20:
            return None
        sport, dport = struct.unpack_from("!HH", seg)
        data_off = (seg[12] >> 4) * 4
        return src, dst, sport, dport, seg[data_off:]
    except Exception:
        return None


class FlowStats:
    """Lightweight per-flow statistics for live display."""
    def __init__(self, sni: str):
        self.sni       = sni
        self.start     = time.monotonic()
        self.packets   = 0
        self.bytes     = 0
        self.pkt_sizes = []     # first 20 packet sizes
        self.gaps      = []     # inter-packet gaps ms
        self._last_t   = time.monotonic()
        self.verdict   = None   # "AD" / "VIDEO" / "UNKNOWN"

    def add(self, pkt_len: int):
        now = time.monotonic()
        if self.packets > 0:
            g = (now - self._last_t) * 1000
            if g < 2000:
                self.gaps.append(round(g, 1))
        self._last_t = now
        self.packets += 1
        self.bytes   += pkt_len
        if len(self.pkt_sizes) < 20:
            self.pkt_sizes.append(pkt_len)

    def gap_variance(self):
        g = self.gaps
        if len(g) < 4:
            return None
        m = sum(g) / len(g)
        return sum((x - m) ** 2 for x in g) / len(g)

    def age_s(self):
        return time.monotonic() - self.start

    def summary(self):
        gv    = self.gap_variance()
        small = sum(1 for s in self.pkt_sizes if s <= 1460)
        large = sum(1 for s in self.pkt_sizes if s >= 9000)
        is_ad = sni_is_ad(self.sni)
        sizes = self.pkt_sizes[:6]

        label = (f"{RED}{BOLD}[AD PATTERN]{RESET}"   if is_ad else
                 f"{GREEN}{BOLD}[VIDEO     ]{RESET}")

        gv_str = f"{gv:6.1f}" if gv is not None else "   n/a"
        print(
            f"\n{CYAN}{BOLD}{'─'*68}{RESET}\n"
            f"  {label}  {BOLD}{self.sni}{RESET}\n"
            f"  Pkts:{self.packets:4d}  Bytes:{self.bytes/1024:7.1f} KB  "
            f"Age:{self.age_s():5.1f}s  GapVar:{gv_str} ms²\n"
            f"  Small(≤1460B):{small:3d}  Large(≥9000B):{large:3d}\n"
            f"  First sizes: {sizes}"
        )
        if is_ad:
            print(f"  {RED}↳ adstream.py WOULD DROP this flow{RESET}")
        else:
            print(f"  {GREEN}↳ adstream.py would ALLOW this flow{RESET}")


def main():
    if os.geteuid() != 0:
        print(f"{RED}Must run as root (sudo){RESET}")
        sys.exit(1)

    print(f"\n{BOLD}{CYAN}Overheard — Live YouTube Traffic Capture{RESET}")
    print(f"{DIM}Watching TLS port 443 traffic. Open YouTube and play a video.{RESET}")
    print(f"{DIM}Press Ctrl-C to stop.\n{RESET}")

    # Raw socket — capture all IP traffic
    try:
        sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0800))
    except AttributeError:
        # macOS fallback (AF_PACKET not available; use BPF via pcap hint)
        print(f"{YELLOW}AF_PACKET not available on macOS. Run this on the board (Linux).{RESET}")
        print(f"{DIM}On the board: sudo python3 live_capture.py{RESET}")
        sys.exit(0)

    flows      = {}            # flow_id → FlowStats
    seen_snis  = set()
    pkt_count  = 0
    start      = time.monotonic()

    try:
        while True:
            raw, _ = sock.recvfrom(65535)
            # Ethernet frame: skip 14-byte header
            if len(raw) < 14:
                continue
            ip = raw[14:]
            parsed = parse_ip_tcp(ip)
            if not parsed:
                continue
            src, dst, sport, dport, payload = parsed

            if dport != 443 and sport != 443:
                continue

            pkt_count += 1
            flow_id = f"{src}:{sport}→{dst}:{dport}"

            # Try to extract SNI from ClientHello
            if dport == 443 and payload and flow_id not in flows:
                sni = extract_sni(payload)
                if sni and is_youtube(sni):
                    flows[flow_id] = FlowStats(sni)
                    if sni not in seen_snis:
                        seen_snis.add(sni)
                        verdict = "AD" if sni_is_ad(sni) else "VIDEO"
                        color   = RED if verdict == "AD" else GREEN
                        print(f"  {color}[NEW {verdict:5}]{RESET}  {sni}")

            # Accumulate stats for known flows
            if flow_id in flows:
                flows[flow_id].add(len(payload))

                # Print a summary every 20 packets for this flow
                fs = flows[flow_id]
                if fs.packets in (10, 20, 50, 100):
                    fs.summary()

            # Periodic header with totals
            age = time.monotonic() - start
            if pkt_count % 500 == 0:
                print(f"\n  {DIM}── {pkt_count} pkts captured | "
                      f"{len(flows)} YT flows | "
                      f"{sum(1 for f in flows.values() if sni_is_ad(f.sni))} ad flows | "
                      f"{age:.0f}s elapsed ──{RESET}")

    except KeyboardInterrupt:
        print(f"\n\n{BOLD}── Final Summary ──────────────────────────────────────{RESET}")
        for fid, fs in sorted(flows.items(), key=lambda x: -x[1].bytes):
            fs.summary()

        ad_flows    = [f for f in flows.values() if sni_is_ad(f.sni)]
        video_flows = [f for f in flows.values() if not sni_is_ad(f.sni)]
        total_bytes = sum(f.bytes for f in flows.values())

        print(f"\n{BOLD}  Total YouTube flows : {len(flows)}{RESET}")
        print(f"  {RED}Ad flows             : {len(ad_flows)}{RESET}")
        print(f"  {GREEN}Video flows          : {len(video_flows)}{RESET}")
        print(f"  Total bytes          : {total_bytes/1024/1024:.2f} MB")
        print(f"  Packets captured     : {pkt_count}")


if __name__ == "__main__":
    main()
