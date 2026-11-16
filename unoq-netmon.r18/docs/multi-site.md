# Two sites, one network
Goal: a DNS board at home (own router and modem, so the board can be the network's DNS for everything) and one at the apartment, each with its own dashboard, and one dashboard that also shows the other.

## Built (r19)
- Client tools find a board through `board.conf`, `sites/<name>.conf` (pick with `SITE=<name>`) or `BOARD_HOST=<address>` (r18).
- Read-only summary of the other boards. A board with `<data_dir>/peers.json` (mode 600) lists its peers; with no file nothing changes. Format: `{"site": "apartment", "peers": [{"name": "home", "url": "http://100.64.0.1:8080", "key": "<that board's access key>"}]}`.
- The board asks each peer's existing `GET /api/stats` over Tailscale with that peer's access key only, never an unlock session. Only the peer's locked view crosses: totals, rates, device labels, vitals, and no looked-up names. Domains stay on the board that saw them (open its own dashboard and unlock there). Whatever a peer sends is rebuilt from known fields before the page sees it, so an unlocked-shaped reply cannot carry a name through.
- A peer needs no update: an r17 or r18 board works as a peer of a new board as is.
- Outbound guard: http or https to a literal Tailscale address (100.64.0.0/10) only, no names; no redirects; the whole request ends after 4 s (2 s per read); 256 KB cap; 2 s cache; one request at a time per peer; at most 8 peers.
- API: `GET /api/sites` (names and state, never addresses or keys), `GET /api/site?name=home` (that board's locked stats, 502 `site unreachable` when it is down). Both sit behind the access key.
- Dashboard: with more than one site, pills at the top switch the view; a banner says it is a summary and unlock, settings, LED and profile controls are hidden while viewing another board.
- Owner tool: `Link Sites.command` (Mac) reads each board's key over SSH and writes `peers.json` on every board listing the others, then restarts the service. Needs two or more `sites/*.conf`, each with the board's Tailscale address as BOARD_HOST. Reading is all or nothing: if any board cannot be read, nothing is written to any board. Writing is **not** atomic (one SSH session per board): if a write fails part-way it stops and exits non-zero, and `last-link-sites.txt` lists which boards were written (`ok`) and which were `not written`; the written ones keep their new list. Keys are never shown or saved on the Mac. Result: `~/Desktop/ArduinoQ/last-link-sites.txt`. Re-run it after a board's key changes.

## Not built
- Each board keeps its own database and decisions; nothing is merged.
- Sync of the allow-list and the extra blocklist (one site as source of truth).
- Fingerprints are never shared.
- A relay on the VPS for boards that cannot reach each other directly (it would hold no data).
- Home site: set the router's DHCP DNS (option 6) to the home board so every device gets it (Lane A in docs/auto-dns.md).

## Not tested on real boards
Tailscale reachability, the `.command` on a Mac, and the pills on a phone. Tests use local fake peers.

## Open
Which site is the source of truth for lists; whether to share fingerprints at all (privacy); what happens when one board is offline (clients need a fallback resolver).
