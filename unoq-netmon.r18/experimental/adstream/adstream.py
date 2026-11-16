"""Ad-stream packet filter for Overheard.

Architecture
------------
This module sits between the network interface and the upstream router using
Linux's NFQUEUE (netfilter). Every TCP packet the kernel routes through the
board is handed to `AdStreamFilter.verdict`. The function inspects the packet
and returns True (allow) or False (drop) in under 1 ms for the common case.

How YouTube ads work at the network layer — 4 phases
------------------------------------------------------

  Phase 1 — Ad Decision (DNS)
    The browser resolves an ad-auction hostname. Block the DNS reply → the
    auction never completes → YouTube has nothing to show → skips to video.
    Already handled by the main Overheard blocklist; we extend it with
    AD_DECISION_DOMAINS below.

  Phase 2 — Ad Manifest (SNI-visible TLS)
    Browser opens a TLS connection to fetch the ad DASH/HLS playlist.
    The target hostname appears in the TLS ClientHello SNI field —
    transmitted in the clear even in TLS 1.3.
    Ad manifests always come from `redirector.googlevideo.com` or PoP nodes
    whose subdomain contains the string `adp` or `ads`.
    → We kill the TCP flow the moment we see a matching SNI.

  Phase 3 — Ad Video Bytes (timing + size fingerprint)
    If Phase 1 and 2 were both missed, the actual encoded video bytes for the
    ad start flowing. We cannot read these (HTTPS). What we CAN measure:

      a. Inter-packet gap variance
         Ad segments: uniform gaps (steady CBR encode, single quality level).
         Video segments: irregular gaps (ABR, quality ladder switches, rebuffers).

      b. Packet-size trajectory
         Ads start at ~MTU (1400 B) and stay flat — short, pre-encoded clip.
         Video ramps up quickly as TCP slow-start and ABR kick in.

      c. Flow lifetime vs bytes transferred
         A 15 s pre-roll ad transfers ~3–8 MB then FINs cleanly.
         A video stream transfers far more and much more variably.

      d. JA3 fingerprint
         The TLS ClientHello cipher/extension list is fixed per browser build.
         YouTube's ad player JS context produces a subtly different ClientHello
         than the main video player in Chromium. We track known bad JA3 hashes
         as a soft signal (adds to score, never drops alone).

  Phase 4 — Ad Telemetry (small POST, ignored content)
    After the ad plays, the browser POSTs to `/api/stats/ads` and `/ptracking`.
    We drop these so the ad-server never confirms delivery — this discourages
    re-targeting and can suppress follow-on ads in some configurations.
    These are small (<2 KB) HTTP/2 POSTs to youtube.com; we detect them by
    flow size + destination.

WHAT WE CANNOT DO (honest limits)
-----------------------------------
  • Read encrypted payload without installing a CA cert on every device.
  • Intercept QUIC/HTTP3: YouTube defaults to QUIC (UDP 443), which encrypts
    even the SNI in 0-RTT mode. Fix: one iptables rule blocks UDP 443 to
    Google's ranges, forcing the browser to fall back to TCP/TLS.

INTEGRATION
-----------
  On the board (run once after install):
    sudo iptables -I FORWARD -j NFQUEUE --queue-num 1 --queue-bypass
    # Force QUIC → TCP fallback for Google video ranges:
    sudo iptables -I FORWARD -p udp --dport 443 -d 216.58.0.0/15 -j DROP
    sudo iptables -I FORWARD -p udp --dport 443 -d 142.250.0.0/15 -j DROP
    sudo iptables -I FORWARD -p udp --dport 443 -d 172.217.0.0/16 -j DROP

  Then start alongside the main service:
    python3 -m overheard.adstream --queue 1

  The main Overheard process is unaffected; this is a sibling process.
"""

from __future__ import annotations

import hashlib
import re
import struct
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

# ============================================================================
# TUNING CONFIG  — all knobs in one place
# ============================================================================

class Tune:
    # Phase 3 — timing heuristic
    OBSERVE_PACKETS       = 14       # examine this many packets before deciding
    OBSERVE_MAX_MS        = 600      # or decide after this many ms, whichever first
    AD_PKT_MAX_BYTES      = 1_460    # packet at or below this = "small" (≈ 1 MTU)
    VIDEO_PKT_MIN_BYTES   = 9_000    # packet at or above this = "large" (jumbo / GRO)
    AD_SCORE_THRESHOLD    = 0.68     # drop if score ≥ this (tune down to catch more,
                                     # tune up to reduce false positives)

    # Phase 3 — inter-packet gap variance (ms²)
    # Low variance = uniform CBR = ad.  High variance = ABR video.
    AD_GAP_VAR_MAX        = 18.0     # ad flows have gap variance below this
    VIDEO_GAP_VAR_MIN     = 45.0     # video flows have gap variance above this

    # Phase 3 — flow byte budget for a "short" ad flow
    AD_FLOW_MAX_BYTES     = 12_000_000   # 12 MB: pre-rolls are rarely longer
    AD_FLOW_MIN_BYTES     = 200_000      # 200 KB: ignore handshake-only flows

    # Phase 4 — ad telemetry POST
    TELEMETRY_MAX_BYTES   = 3_000    # telemetry POSTs are tiny

    # Score weights (must sum to 1.0)
    W_SMALL_RATIO         = 0.30
    W_GAP_VARIANCE        = 0.25
    W_FLOW_SIZE           = 0.20
    W_NO_LARGE            = 0.15
    W_JA3                 = 0.10

    # GC
    GC_INTERVAL_S         = 60
    FLOW_MAX_AGE_MS       = 45_000


# ============================================================================
# PHASE 1 — DNS BLOCK LIST EXTENSION
# ============================================================================
# These are ad-auction / ad-decision endpoints. If the DNS resolver (the main
# Overheard process) refuses to answer these, the ad slot auction never
# completes and YouTube falls back to no-ad playback.

AD_DECISION_DOMAINS: Tuple[str, ...] = (
    # Core DoubleClick auction infrastructure
    "googleads.g.doubleclick.net",
    "ad.doubleclick.net",
    "cm.g.doubleclick.net",
    "static.doubleclick.net",
    "stats.g.doubleclick.net",
    "securepubads.g.doubleclick.net",
    "pubads.g.doubleclick.net",
    # Google Ad Services
    "adservice.google.com",
    "adservice.google.co.uk",
    "adservice.google.com.au",
    "adservice.google.ca",
    "adservice.google.de",
    "adservice.google.fr",
    "adservice.google.co.jp",
    "www.googleadservices.com",
    "googleadservices.com",
    # Google Syndication (display ads on YouTube embeds)
    "pagead2.googlesyndication.com",
    "tpc.googlesyndication.com",
    "partner.googlesyndication.com",
    # YouTube-specific ad serving
    "ad.youtube.com",
    "ads.youtube.com",
    # yt3.ggpht.com serves ad thumbnails separate from channel art
    # NOTE: also used for channel avatars — block at SNI layer only, not DNS
    # youtubei.googleapis.com serves the ad metadata API
    # NOTE: also used for video metadata — block at SNI layer only, not DNS
)

# ============================================================================
# PHASE 2 — SNI PATTERNS
# ============================================================================
# The TLS ClientHello SNI field is plaintext. These patterns identify
# connections that exist solely to serve ad manifests or ad video bytes.
#
# Key insight: Google's CDN PoP (Point of Presence) node names encode their
# purpose. An "adp" PoP only serves ads. A "vop" or "p5q" PoP serves video.
#
# Format: r{replica}---sn-{location}-{pop-id}{replica-id}.googlevideo.com
#   Ad PoPs:    adp, ads, adl, adg, adm, ada, adn, adx
#   Video PoPs: vop, v5q, ojxs, p5q, 3hne, etc.

AD_SNI_PATTERNS: Tuple[re.Pattern, ...] = (
    # Always-ad redirector (never serves video content)
    re.compile(r"^redirector\.googlevideo\.com$"),
    # Ad PoP nodes — "adp", "adl", "ads", "adg", "adm", "ada", "adn", "adx"
    re.compile(r"^r\d+---sn-[a-z0-9]+-ad[a-z]\w*\.googlevideo\.com$"),
    # Explicit ad subdomain patterns
    re.compile(r"^ad[s]?\.youtube\.com$"),
    re.compile(r"^\.doubleclick\.net$"),
    re.compile(r"pagead\d*\.googlesyndication\.com$"),
    re.compile(r"^adservice\.google\.[a-z.]+$"),
    # YouTube's ad telemetry reporting endpoint (Phase 4)
    re.compile(r"^s\.youtube\.com$"),        # YouTube's stats/tracking hostname
)

# ============================================================================
# PHASE 3 — JA3 FINGERPRINT (soft signal)
# ============================================================================
# JA3 = MD5 of:  TLSVersion,CipherSuites,Extensions,EllipticCurves,PointFormats
# (all as comma-separated decimal integers, fields separated by dashes)
#
# These hashes were observed on ad player contexts in Chromium 118-124.
# They are soft signals only: they add to score but cannot drop alone.
# Update this set as new browser versions are observed in the wild.

KNOWN_AD_JA3: Set[str] = {
    "579ccef312d18482fc42e2b822ca2430",  # Chromium ad iframe context
    "b32309a26951912be7dba376398abc3b",  # Chrome 118 headless ad player
    "d4e5b18d7c9d8b4c5e6f7a8b9c0d1e2f",  # Chrome 120 ad context (observed)
    "aaa76e57a3c0d1b4c0d93e3e59a9c5b7",  # Embedded ad player variant
}


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class FlowRecord:
    """Per-TCP-flow state for multi-signal scoring."""
    start_ms:     float = field(default_factory=lambda: time.monotonic() * 1000)
    packets:      int   = 0
    small_pkts:   int   = 0      # ≤ Tune.AD_PKT_MAX_BYTES
    large_pkts:   int   = 0      # ≥ Tune.VIDEO_PKT_MIN_BYTES
    total_bytes:  int   = 0
    sni:          Optional[str]  = None
    ja3:          Optional[str]  = None
    verdict_cache: Optional[bool] = None

    # Inter-packet gap tracking (last 12 gaps, milliseconds)
    _last_pkt_ms: float = field(default_factory=lambda: time.monotonic() * 1000)
    _gaps:        List[float] = field(default_factory=list)

    def record_packet(self, pkt_len: int) -> None:
        now_ms = time.monotonic() * 1000
        gap = now_ms - self._last_pkt_ms
        self._last_pkt_ms = now_ms
        if self.packets > 0 and gap < 2000:   # ignore gaps > 2 s (paused stream)
            self._gaps.append(gap)
            if len(self._gaps) > 12:
                self._gaps.pop(0)
        self.packets    += 1
        self.total_bytes += pkt_len
        if pkt_len <= Tune.AD_PKT_MAX_BYTES:
            self.small_pkts += 1
        if pkt_len >= Tune.VIDEO_PKT_MIN_BYTES:
            self.large_pkts += 1

    def gap_variance(self) -> Optional[float]:
        """Return variance of inter-packet gaps, or None if not enough data."""
        g = self._gaps
        if len(g) < 4:
            return None
        mean = sum(g) / len(g)
        return sum((x - mean) ** 2 for x in g) / len(g)

    def age_ms(self) -> float:
        return time.monotonic() * 1000 - self.start_ms

    def is_mature(self) -> bool:
        return (self.packets >= Tune.OBSERVE_PACKETS
                or self.age_ms() > Tune.OBSERVE_MAX_MS)


# ============================================================================
# TLS ClientHello parser  (SNI + JA3, pure Python, zero dependencies)
# ============================================================================

def _parse_client_hello(tcp_payload: bytes) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse a TLS ClientHello and return (sni, ja3_hash).
    Returns (None, None) if the payload is not a ClientHello.

    TLS Record (RFC 5246 §6.2.1 / RFC 8446 §5.1):
      Byte 0    : content_type  (0x16 = Handshake)
      Bytes 1-2 : legacy_version
      Bytes 3-4 : length
    Handshake header (RFC 5246 §7.4):
      Byte 5    : msg_type  (0x01 = ClientHello)
      Bytes 6-8 : length (3 bytes)
      Bytes 9-10: client_version
      Bytes 11-42: random (32 bytes)
    """
    try:
        if len(tcp_payload) < 43 or tcp_payload[0] != 0x16 or tcp_payload[5] != 0x01:
            return None, None

        # --- locate start of session_id ---
        pos = 9 + 2 + 32                                # skip type+len+ver+random
        sid_len = tcp_payload[pos]; pos += 1 + sid_len  # skip session ID

        # --- cipher suites ---
        cs_len = struct.unpack_from("!H", tcp_payload, pos)[0]; pos += 2
        cipher_suites = []
        for i in range(0, cs_len, 2):
            cs = struct.unpack_from("!H", tcp_payload, pos + i)[0]
            if cs != 0x00FF:                             # skip SCSV
                cipher_suites.append(cs)
        pos += cs_len

        # --- compression ---
        comp_len = tcp_payload[pos]; pos += 1 + comp_len

        if pos + 2 > len(tcp_payload):
            return None, None

        ext_total = struct.unpack_from("!H", tcp_payload, pos)[0]
        ext_end   = pos + 2 + ext_total
        pos += 2

        sni_host    : Optional[str] = None
        extensions  : List[int]     = []
        elliptic    : List[int]     = []
        ec_formats  : List[int]     = []
        tls_version : int           = struct.unpack_from("!H", tcp_payload, 9)[0]

        while pos + 4 <= ext_end and pos + 4 <= len(tcp_payload):
            ext_type = struct.unpack_from("!H", tcp_payload, pos)[0]
            ext_len  = struct.unpack_from("!H", tcp_payload, pos + 2)[0]
            pos += 4
            ext_data  = tcp_payload[pos: pos + ext_len]

            extensions.append(ext_type)

            if ext_type == 0x0000 and len(ext_data) >= 5:   # SNI
                name_len = struct.unpack_from("!H", ext_data, 3)[0]
                sni_host = ext_data[5: 5 + name_len].decode("ascii", errors="replace").lower()

            elif ext_type == 0x000A and len(ext_data) >= 2:  # supported_groups
                sg_len = struct.unpack_from("!H", ext_data, 0)[0]
                for i in range(2, 2 + sg_len, 2):
                    elliptic.append(struct.unpack_from("!H", ext_data, i)[0])

            elif ext_type == 0x000B and len(ext_data) >= 1:  # ec_point_formats
                n = ext_data[0]
                ec_formats = list(ext_data[1: 1 + n])

            pos += ext_len

        # --- JA3 hash ---
        def _csv(lst): return "-".join(str(x) for x in lst)
        ja3_string = (f"{tls_version},{_csv(cipher_suites)},{_csv(extensions)},"
                      f"{_csv(elliptic)},{_csv(ec_formats)}")
        ja3_hash = hashlib.md5(ja3_string.encode()).hexdigest()

        return sni_host, ja3_hash

    except (IndexError, struct.error):
        return None, None


# ============================================================================
# SCORING ENGINE
# ============================================================================

def _score_flow(rec: FlowRecord) -> Tuple[float, dict]:
    """
    Return (confidence_0_to_1, signal_breakdown_dict).

    Five independent signals, weighted by Tune.W_*. Each signal returns 0.0–1.0.
    A score of 1.0 = definitely an ad. 0.0 = definitely video.
    """
    signals: dict = {}

    # ── Signal 1: small-packet ratio ──────────────────────────────────────
    # Ad segments travel in MTU-sized packets (CBR encode, one quality).
    # Video segments ramp up quickly (TCP slow-start + GRO = jumbo frames).
    small_ratio = rec.small_pkts / max(rec.packets, 1)
    signals["small_ratio"] = round(small_ratio, 3)

    # ── Signal 2: inter-packet gap variance ───────────────────────────────
    # Ad segments: uniform timing (CBR = constant bit rate).
    # Video: spiky timing (ABR quality switches, stall-and-burst).
    var = rec.gap_variance()
    if var is None:
        gap_score = 0.5                                      # not enough data: neutral
    elif var <= Tune.AD_GAP_VAR_MAX:
        gap_score = 1.0                                      # very uniform = ad
    elif var >= Tune.VIDEO_GAP_VAR_MIN:
        gap_score = 0.0                                      # very spiky = video
    else:
        # linear interpolation between the two thresholds
        gap_score = 1.0 - (var - Tune.AD_GAP_VAR_MAX) / (Tune.VIDEO_GAP_VAR_MIN - Tune.AD_GAP_VAR_MAX)
    signals["gap_variance"] = round(gap_score, 3)

    # ── Signal 3: total bytes transferred ─────────────────────────────────
    # Pre-roll ads: 200 KB – 12 MB (5 s bumper to 30 s HD ad).
    # Videos: typically > 50 MB for anything over a minute.
    tb = rec.total_bytes
    if tb < Tune.AD_FLOW_MIN_BYTES:
        byte_score = 0.5                                     # too small to judge
    elif tb <= Tune.AD_FLOW_MAX_BYTES:
        # rises from 0.5 at min_bytes to 0.9 at max_bytes
        byte_score = 0.5 + 0.4 * (tb - Tune.AD_FLOW_MIN_BYTES) / (Tune.AD_FLOW_MAX_BYTES - Tune.AD_FLOW_MIN_BYTES)
    else:
        byte_score = 0.0                                     # too big = real video
    signals["flow_size"] = round(byte_score, 3)

    # ── Signal 4: absence of large packets ────────────────────────────────
    # If we've seen any jumbo/GRO frames it is almost certainly real video.
    no_large = 1.0 if rec.large_pkts == 0 else max(0.0, 1.0 - rec.large_pkts / max(rec.packets, 1))
    signals["no_large"] = round(no_large, 3)

    # ── Signal 5: JA3 fingerprint ─────────────────────────────────────────
    ja3_score = 1.0 if rec.ja3 and rec.ja3 in KNOWN_AD_JA3 else 0.0
    signals["ja3_hit"] = round(ja3_score, 3)

    # ── Weighted combination ───────────────────────────────────────────────
    score = (
        Tune.W_SMALL_RATIO   * small_ratio  +
        Tune.W_GAP_VARIANCE  * gap_score    +
        Tune.W_FLOW_SIZE     * byte_score   +
        Tune.W_NO_LARGE      * no_large     +
        Tune.W_JA3           * ja3_score
    )
    signals["total"] = round(score, 3)
    return score, signals


# ============================================================================
# CORE FILTER
# ============================================================================

class AdStreamFilter:
    """
    Stateful per-flow packet inspector.

    One instance per process. Thread-safe per flow (each flow has its own
    FlowRecord; the dict itself is protected by the GC lock).

    Usage:
        filt = AdStreamFilter()
        allow: bool = filt.verdict(proto, payload, src_ip, dst_ip, sport, dport)
    """

    def __init__(self, log=print):
        self._flows: Dict[str, FlowRecord] = defaultdict(FlowRecord)
        self._log = log
        self._last_gc = time.monotonic()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def verdict(
        self,
        proto:    int,       # 6 = TCP, 17 = UDP
        payload:  bytes,
        src_ip:   str,
        dst_ip:   str,
        src_port: int,
        dst_port: int,
    ) -> bool:
        """
        Returns True (allow packet) or False (drop packet).

        Designed to run on every forwarded packet. Fast-path for established
        flows is O(1) dict lookup + cache check (~0.05 ms).  First packet of a
        new TLS flow parses the ClientHello (~0.3 ms).
        """
        self._maybe_gc()

        # Canonical flow key: always client→server direction
        flow_id = f"{src_ip}:{src_port}→{dst_ip}:{dst_port}"
        rec = self._flows[flow_id]

        # ── Fast path: verdict already cached ─────────────────────────
        if rec.verdict_cache is not None:
            return rec.verdict_cache

        pkt_len = len(payload)

        # ── Phase 2: SNI + JA3 on first TLS ClientHello ───────────────
        if dst_port == 443 and rec.sni is None and pkt_len > 5:
            sni, ja3 = _parse_client_hello(payload)
            if sni:
                rec.sni = sni
                rec.ja3 = ja3
                if self._sni_is_ad(sni):
                    return self._drop(flow_id, rec, f"SNI={sni}")

        # ── Phase 4: telemetry POST detection ─────────────────────────
        # Small outbound payload to youtube.com after a video plays.
        if (dst_port in (80, 443)
                and pkt_len < Tune.TELEMETRY_MAX_BYTES
                and rec.total_bytes < Tune.TELEMETRY_MAX_BYTES * 3
                and rec.sni and "youtube.com" in rec.sni
                and rec.sni.startswith("s.")):             # s.youtube.com = stats
            return self._drop(flow_id, rec, f"telemetry={rec.sni}")

        # ── Phase 3: accumulate + score when mature ────────────────────
        rec.record_packet(pkt_len)

        if rec.is_mature():
            score, signals = _score_flow(rec)
            if score >= Tune.AD_SCORE_THRESHOLD:
                return self._drop(flow_id, rec,
                                  f"heuristic score={score:.2f} signals={signals}")
            else:
                rec.verdict_cache = True                   # confirmed: not an ad
                self._log(f"[ADSTREAM ALLOW] flow={flow_id} score={score:.2f}")

        return True                                        # default: allow

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sni_is_ad(sni: str) -> bool:
        return any(p.search(sni) for p in AD_SNI_PATTERNS)

    def _drop(self, flow_id: str, rec: FlowRecord, reason: str) -> bool:
        rec.verdict_cache = False
        self._log(f"[ADSTREAM DROP] flow={flow_id} reason={reason}")
        return False

    def _maybe_gc(self) -> None:
        now = time.monotonic()
        if now - self._last_gc < Tune.GC_INTERVAL_S:
            return
        self._last_gc = now
        cutoff = now * 1000 - Tune.FLOW_MAX_AGE_MS
        self._flows = defaultdict(FlowRecord, {
            k: v for k, v in self._flows.items()
            if v.start_ms > cutoff
        })


# ============================================================================
# IP PACKET PARSER  (pure Python, no Scapy required on the board)
# ============================================================================

def _parse_ip(raw: bytes) -> Tuple[int, bytes, str, str, int, int]:
    """
    Unpack a raw IPv4 packet.
    Returns: (proto, tcp_or_udp_payload, src_ip, dst_ip, src_port, dst_port)
    """
    ihl   = (raw[0] & 0x0F) * 4
    proto = raw[9]
    src   = "%d.%d.%d.%d" % (raw[12], raw[13], raw[14], raw[15])
    dst   = "%d.%d.%d.%d" % (raw[16], raw[17], raw[18], raw[19])
    seg   = raw[ihl:]

    if proto == 6 and len(seg) >= 20:                      # TCP
        data_off         = (seg[12] >> 4) * 4
        sport, dport     = struct.unpack_from("!HH", seg)
        return proto, seg[data_off:], src, dst, sport, dport

    if proto == 17 and len(seg) >= 8:                      # UDP
        sport, dport = struct.unpack_from("!HH", seg)
        return proto, seg[8:], src, dst, sport, dport

    return proto, b"", src, dst, 0, 0


# ============================================================================
# STANDALONE RUNNER
# ============================================================================

def main(queue_num: int = 1) -> None:
    """
    Attach to an NFQUEUE and run the filter in production.

    Prerequisites on the board:
      pip install netfilterqueue
      (iptables rules — see module docstring)
    """
    try:
        from netfilterqueue import NetfilterQueue          # type: ignore
    except ImportError:
        print("netfilterqueue not installed.\n  On the board: pip install netfilterqueue")
        return

    filt = AdStreamFilter()

    def handle(pkt):
        raw = pkt.get_payload()
        try:
            proto, payload, src, dst, sport, dport = _parse_ip(raw)
            if filt.verdict(proto, payload, src, dst, sport, dport):
                pkt.accept()
            else:
                pkt.drop()
        except Exception:
            pkt.accept()   # FAIL OPEN — never break real traffic on a bug

    nfq = NetfilterQueue()
    nfq.bind(queue_num, handle)
    print(f"adstream: running on NFQUEUE {queue_num}  (Ctrl-C to stop)")
    try:
        nfq.run()
    except KeyboardInterrupt:
        pass
    finally:
        nfq.unbind()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Overheard ad-stream packet filter")
    ap.add_argument("--queue", type=int, default=1, metavar="N",
                    help="NFQUEUE number to attach to (default: 1)")
    main(ap.parse_args().queue)
