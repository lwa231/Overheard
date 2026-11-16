# Two sites, one network (plan; r18 only adds the configurable address)
Goal: a DNS board at home (own router and modem, so the board can be the network's DNS for everything) and one at the apartment (today's board), able to share data, possibly through the VPS.

## What r18 changes
Only where the client tools find a board: `board.conf` (default), `sites/<name>.conf` (pick with `SITE=<name>`), or `BOARD_HOST=<address>` for one run. Everything else is as in r17. Nothing runs between sites yet.

## Planned shape (not built)
- Both boards join the same Tailscale network, so each reaches the other by its stable address, from any Wi-Fi.
- Each board keeps its own database and decisions; nothing is merged without a rule.
- Read-only sharing first: one board reads the other's `/api/stats` over Tailscale with its own access key (the locked view carries no domains; domains only after the user unlocks).
- Later: sync the allow-list and the extra blocklist between boards (one site is the source of truth), and one combined view in the dashboard (a tab per site).
- The VPS can be a relay only when two boards cannot reach each other directly; it holds no data of its own.
- Home site: set the router's DHCP DNS (option 6) to the home board so every device gets it with no per-device setup (Lane A in docs/auto-dns.md).
## Open
Which site is the source of truth for lists; whether to share fingerprints at all (privacy); per-site access keys; what happens when one board is offline (clients need a fallback resolver).
