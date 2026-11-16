# experimental/

Parked code. Nothing here ships, is imported by `src/`, is covered by a test, or has been run.
It was added unreviewed in r15 (Gemini) and staged here in r16. Do not wire it in without a design review.

## adstream/

| File | What it is |
|---|---|
| `adstream.py` | Packet filter for ad streams (TLS SNI patterns, JA3-style fingerprints, flow tracking). Meant to run on a Linux NFQUEUE. |
| `live_capture.py` | Standalone root-only AF_PACKET sniffer that prints SNI names and what `adstream.py` would do. |
| `live_youtube_traffic.py` | Larger sibling of `live_capture.py` for macOS/Linux, with colour output. |
| `dpi_packet_filter.py` | Non-functional "TLS decryption" skeleton. Calls functions that do not exist. Reference only. |

## Known problems

- Unshipped and untested. No test imports these files; `ruff` is told to skip this directory (see `pyproject.toml`).
- `adstream.py` needs `netfilterqueue` (pip, C extension) and an iptables FORWARD rule. That breaks the
  project's stdlib-only rule.
- Some patterns are wrong (for example `^\.doubleclick\.net$` can never match) and some JA3 hashes look
  made up. See `docs/r16-audit.md`.
- The flow table grows without a bound under a flood.

## Why it cannot work as deployed

The board is only a DNS server for the LAN. It sees DNS queries, not the video streams between clients and
the internet, so it cannot inspect or drop streams. That would need client traffic routed through the board
(it as the gateway) or through a VPS exit node (VPN). In-stream YouTube ads come from googlevideo.com,
which DNS blocking cannot separate from real video.
