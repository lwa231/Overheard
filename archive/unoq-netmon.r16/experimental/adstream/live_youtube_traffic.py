#!/usr/bin/env python3
"""
Live YouTube Traffic Monitor & Ad Filter Analyzer
==================================================
Runs on macOS or Linux to inspect YouTube streaming packets in real-time.
Shows TLS SNI hostnames, packet sizes, flow timing, and the adstream.py verdict.

Usage:
    sudo python3 live_youtube_traffic.py [interface]

Examples:
    macOS:  sudo python3 live_youtube_traffic.py en0
    Linux:  sudo python3 live_youtube_traffic.py eth0
"""

import os
import re
import select
import struct
import subprocess
import sys
import time
from collections import defaultdict
from typing import Optional, Tuple

# ── ANSI Colors ─────────────────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
RED     = "\033[91m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
CYAN    = "\033[96m"
MAGENTA = "\033[95m"

# ── Ad Host & SNI Patterns (from adstream.py) ──────────────────────────────
AD_SNI_PATTERNS = (
    re.compile(r"^redirector\.googlevideo\.com$"),
    re.compile(r"^r\d+---sn-[a-z0-9]+-ad[a-z]\w*\.googlevideo\.com$"),
    re.compile(r"^ad[s]?\.youtube\.com$"),
    re.compile(r"pagead\d*\.googlesyndication\.com$"),
    re.compile(r"^adservice\.google\.[a-z.]+$"),
    re.compile(r"^s\.youtube\.com$"),
    re.compile(r"\.doubleclick\.net$"),
    re.compile(r"googleads\.g\.doubleclick\.net$"),
)

YOUTUBE_DOMAINS = (
    "googlevideo.com",
    "youtube.com",
    "googlesyndication.com",
    "doubleclick.net",
    "googleadservices.com",
    "ytimg.com",
    "ggpht.com",
    "googleapis.com",
)

def is_youtube_host(sni: str) -> bool:
    return any(sni == d or sni.endswith("." + d) for d in YOUTUBE_DOMAINS)

def is_ad_sni(sni: str) -> bool:
    return any(p.search(sni) for p in AD_SNI_PATTERNS)

# ── TLS SNI Extractor ───────────────────────────────────────────────────────
def extract_sni_from_payload(payload: bytes) -> Optional[str]:
    """Extracts Server Name Indication (SNI) from TLS ClientHello."""
    try:
        if len(payload) < 43:
            return None
        # TLS record header: 0x16 is Handshake
        if payload[0] != 0x16:
            return None
        # Handshake message type: 0x01 is ClientHello
        if payload[5] != 0x01:
            return None

        # Jump to session ID length
        pos = 9 + 2 + 32  # header (5) + handshake (4) + ver (2) + random (32)
        if pos >= len(payload):
            return None
        sid_len = payload[pos]
        pos += 1 + sid_len

        # Cipher suites
        if pos + 2 > len(payload):
            return None
        cs_len = struct.unpack_from("!H", payload, pos)[0]
        pos += 2 + cs_len

        # Compression methods
        if pos + 1 > len(payload):
            return None
        comp_len = payload[pos]
        pos += 1 + comp_len

        # Extensions
        if pos + 2 > len(payload):
            return None
        ext_total = struct.unpack_from("!H", payload, pos)[0]
        ext_end = pos + 2 + ext_total
        pos += 2

        while pos + 4 <= ext_end and pos + 4 <= len(payload):
            ext_type = struct.unpack_from("!H", payload, pos)[0]
            ext_len = struct.unpack_from("!H", payload, pos + 2)[0]
            pos += 4
            if ext_type == 0x0000 and ext_len >= 5:  # SNI extension
                name_len = struct.unpack_from("!H", payload, pos + 3)[0]
                host = payload[pos + 5 : pos + 5 + name_len]
                return host.decode("ascii", errors="replace").lower()
            pos += ext_len
    except Exception:
        pass
    return None

# ── IP / TCP Parser ────────────────────────────────────────────────────────
def parse_ipv4_packet(pkt: bytes) -> Optional[Tuple[str, str, int, int, bytes]]:
    """Parse raw IPv4 bytes into (src_ip, dst_ip, sport, dport, payload)."""
    if len(pkt) < 20:
        return None
    version_ihl = pkt[0]
    if (version_ihl >> 4) != 4:
        return None
    ihl = (version_ihl & 0x0F) * 4
    proto = pkt[9]
    if proto != 6:  # TCP only
        return None
    src_ip = socket.inet_ntoa(pkt[12:16])
    dst_ip = socket.inet_ntoa(pkt[16:20])

    tcp_seg = pkt[ihl:]
    if len(tcp_seg) < 20:
        return None
    sport, dport = struct.unpack_from("!HH", tcp_seg)
    data_off = ((tcp_seg[12] >> 4) & 0x0F) * 4
    payload = tcp_seg[data_off:]
    return src_ip, dst_ip, sport, dport, payload

# ── Flow Tracker ───────────────────────────────────────────────────────────
class FlowTracker:
    def __init__(self, sni: str, flow_id: str):
        self.sni = sni
        self.flow_id = flow_id
        self.start_t = time.monotonic()
        self.last_t = self.start_t
        self.packet_count = 0
        self.total_bytes = 0
        self.small_packets = 0  # <= 1460 bytes
        self.large_packets = 0  # >= 9000 bytes (GRO / jumbo)
        self.gaps = []
        self.is_ad = is_ad_sni(sni)
        self.verdict = "DROP" if self.is_ad else "ALLOW"

    def add_packet(self, pkt_len: int):
        now = time.monotonic()
        gap = (now - self.last_t) * 1000.0
        self.last_t = now
        if self.packet_count > 0 and gap < 2000:
            self.gaps.append(gap)
            if len(self.gaps) > 16:
                self.gaps.pop(0)

        self.packet_count += 1
        self.total_bytes += pkt_len
        if pkt_len <= 1460:
            self.small_packets += 1
        if pkt_len >= 9000:
            self.large_packets += 1

    def gap_variance(self) -> Optional[float]:
        if len(self.gaps) < 4:
            return None
        mean = sum(self.gaps) / len(self.gaps)
        return sum((g - mean) ** 2 for g in self.gaps) / len(self.gaps)

    def print_update(self):
        duration = time.monotonic() - self.start_t
        gv = self.gap_variance()
        gv_str = f"{gv:6.1f} ms²" if gv is not None else "     n/a"
        kb = self.total_bytes / 1024.0

        if self.is_ad:
            tag = f"{RED}{BOLD}[AD STREAM - DROP]{RESET}"
            host_color = RED
        elif "googlevideo.com" in self.sni:
            tag = f"{GREEN}{BOLD}[VIDEO STREAM - ALLOW]{RESET}"
            host_color = GREEN
        else:
            tag = f"{CYAN}[YT METADATA]{RESET}"
            host_color = CYAN

        print(f" {tag} {host_color}{self.sni:<45}{RESET}")
        print(f"      Packets: {self.packet_count:<5} | Bytes: {kb:7.1f} KB | Duration: {duration:4.1f}s | GapVar: {gv_str}")
        print(f"      Small(<=1460B): {self.small_packets} | Jumbo(>=9000B): {self.large_packets} | Flow: {self.flow_id}")
        print(f"      {DIM}{'-'*70}{RESET}")

# ── Main Runner ────────────────────────────────────────────────────────────
def main():
    if os.geteuid() != 0:
        print(f"{RED}{BOLD}Permission denied:{RESET} Please run with {BOLD}sudo python3 {sys.argv[0]}{RESET}")
        sys.exit(1)

    iface = sys.argv[1] if len(sys.argv) > 1 else None

    # Determine command based on platform
    tcpdump_cmd = ["tcpdump", "-U", "-w", "-", "-s", "0", "-n"]
    if iface:
        tcpdump_cmd.extend(["-i", iface])
    tcpdump_cmd.append("tcp port 443")

    print(f"\n{BOLD}{CYAN}=================================================================={RESET}")
    print(f"{BOLD}{CYAN}      Overheard — Live YouTube Traffic & Ad-Stream Inspector     {RESET}")
    print(f"{BOLD}{CYAN}=================================================================={RESET}")
    print(f"  {BOLD}Status:{RESET} Listening for TLS port 443 traffic...")
    print(f"  {BOLD}Action:{RESET} Open YouTube in your browser and play a video.")
    print(f"  {DIM}Command: {' '.join(tcpdump_cmd)}{RESET}")
    print(f"  {DIM}Press Ctrl-C to stop at any time.{RESET}\n")

    try:
        proc = subprocess.Popen(
            tcpdump_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=65536
        )
    except FileNotFoundError:
        print(f"{RED}Error: tcpdump not found on this system.{RESET}")
        sys.exit(1)

    stream = proc.stdout
    if stream is None:
        print(f"{RED}Failed to open tcpdump stream.{RESET}")
        sys.exit(1)

    # Read 24-byte pcap global header
    global_hdr = stream.read(24)
    if len(global_hdr) < 24:
        print(f"{RED}Could not read pcap header. Is the interface up?{RESET}")
        proc.kill()
        sys.exit(1)

    magic, _, _, _, _, _, linktype = struct.unpack("=IHHiIII", global_hdr)
    # Check endianness
    big_endian = (magic == 0xa1b2c3d4)

    flows = {}  # flow_id -> FlowTracker
    endpoint_to_sni = {}  # (dst_ip, dst_port) -> sni
    total_pkts = 0
    ad_drops = 0
    video_allows = 0

    try:
        while True:
            # Read 16-byte packet header
            hdr = stream.read(16)
            if len(hdr) < 16:
                break
            if big_endian:
                _, _, caplen, _ = struct.unpack(">IIII", hdr)
            else:
                _, _, caplen, _ = struct.unpack("<IIII", hdr)

            frame = stream.read(caplen)
            if len(frame) < caplen:
                break

            total_pkts += 1

            # Determine Ethernet / SLL offset
            # DLT_EN10MB = 1 (14 bytes)
            # DLT_LINUX_SLL = 113 (16 bytes)
            # DLT_RAW = 12 (0 bytes)
            # DLT_NULL / Loopback = 0 (4 bytes)
            offset = 14
            if linktype == 113:
                offset = 16
            elif linktype in (12, 101, 228):
                offset = 0
            elif linktype == 0:
                offset = 4

            ip_bytes = frame[offset:]
            parsed = parse_ipv4_packet(ip_bytes)
            if not parsed:
                continue

            src_ip, dst_ip, sport, dport, payload = parsed
            flow_key = f"{src_ip}:{sport}->{dst_ip}:{dport}"
            reverse_flow_key = f"{dst_ip}:{dport}->{src_ip}:{sport}"

            # Check if outbound TLS ClientHello contains SNI
            if dport == 443 and payload:
                sni = extract_sni_from_payload(payload)
                if sni and is_youtube_host(sni):
                    endpoint_to_sni[(dst_ip, dport)] = sni
                    if flow_key not in flows:
                        tracker = FlowTracker(sni, flow_key)
                        flows[flow_key] = tracker
                        flows[reverse_flow_key] = tracker
                        if tracker.is_ad:
                            ad_drops += 1
                        else:
                            video_allows += 1
                        tracker.print_update()

            # Record packet metrics for known YouTube flow
            tracker = flows.get(flow_key) or flows.get(reverse_flow_key)
            if tracker:
                tracker.add_packet(len(payload))
                if tracker.packet_count in (10, 30, 80, 200, 500):
                    tracker.print_update()

    except KeyboardInterrupt:
        print(f"\n\n{BOLD}{CYAN}=== Inspection Complete ==={RESET}")
        print(f"  Total Packets Captured: {total_pkts}")
        print(f"  Active YouTube Flows  : {len(flows) // 2}")
        print(f"  {RED}Ad Streams Detected   : {ad_drops} (Dropped by filter){RESET}")
        print(f"  {GREEN}Video Streams Allowed : {video_allows} (Preserved uninterrupted){RESET}")
        print(f"{BOLD}{CYAN}=================================================================={RESET}\n")
    finally:
        proc.kill()

if __name__ == "__main__":
    main()
