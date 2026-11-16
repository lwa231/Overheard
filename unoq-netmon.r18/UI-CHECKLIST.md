# R17 dashboard checklist (walks `unoq-netmon.r17-design/inventory.md`)

Status: **K** kept as is, **M** moved or restyled (where), **N** not carried over (why). The dashboard was exercised against the demo server only, never the real board.

## 1. Access model
| Item | S | Where / why |
|---|---|---|
| Unlock by brand title or `P`, login sheet, `POST /api/unlock {secret}` | K | brand button, `P`, new Log in button |
| 429 + Retry-After shown as text; empty/wrong/unreachable messages | K | login sheet |
| Lock: `POST /api/lock {}` | M | Lock button in HUD (also `P`, brand) |
| `scrub()` second guard on locked data | K | tested with a leaky reply |
| Locked hero always "Quiet." + protection + N blocked so far | M | under the map title |
| Unlocked hero: service, mode, up to 3 evidence domains | M | same place; evidence is plain text after the mode |
| Latest lookups card, unlocked only | M | own panel beside Board |
| Lookup rows: sub dim, registrable bold, device chip click = focus, blocked tag, strike-through | K | |
| Lookups tally + "Show all" | K | |
| "Flagged" button | M | HUD tools (admin) |
| Pills hidden when locked (Profiles, Skin, Lock) | M | Profiles, Flagged, Look hidden when locked; Lock became Log in / Lock, always visible |
| Status, Encrypted, Refused N, Speed, LED, theme always visible | M | tags and HUD buttons |
| Slowed N pill (admin + slowdown on) with seconds-left title | K | |
| Device tooltips: label + confidence; evidence only unlocked | K | map nodes and matrix headers |
| Keys: `P`, `S`/`Shift+S` (admin), `Esc` closes topmost sheet | K | Esc also clears focus |
| `/api/flagged`, `/api/profile*`, settings POST gated by server | K | no server change |
| Skin switching works only unlocked | K | |
| LED not gated | K | unchanged, as in R16 (owner decision still open) |

## 2. Layout
| Item | S | Where / why |
|---|---|---|
| Three-column full-viewport grid, hero / tiles / matrix / web | N | replaced by the approved layout: HUD, map, readouts, panels |
| Cards radius 26, 1 px border | N | replaced by framed, bracketed panels |
| One-column order on narrow screens | M | breakpoints 1100 and 640; map stays first |

## 3. Views, panels, figures
| Item | S | Where / why |
|---|---|---|
| Brand row and pills | M | HUD |
| Hero headline fit-to-width loop (min 24 px) | N | fixed-size heading that wraps |
| Tile Blocked: count, % of lookups, 10 min sparkline | M | HUD counter |
| Tile Lookups: total, sparkline | M | HUD counter |
| "N devices" under Lookups | M | own Devices counter |
| Tile Download: Mbps, upload in tooltip, 90 s sparkline | M | HUD counter; upload also in NET bar |
| Traffic matrix: device header (dot, name, live/idle, address, lookups) | M | Activity panel; live/idle now uses the board clock |
| Up to 4 service lanes, 120 x 5 s cells, Connection lane | K | |
| Axis, low-high legend | K | legend moves to its own row on phones |
| Hover cell tooltip, hover header = device tooltip, click header = focus | K | |
| Per-skin heat ramps (rainbow default) | N | one accent-derived ramp so every skin and mode stays consistent |
| Latest lookups height-based row count | M | 12 rows (8 on phones) |
| Board meters CPU, Memory, Disk, Temp; "hot" above 85 % | M | Board panel; hot is now red plus a triangle |
| Uptime "Up 3d 4h" | M | Board panel and UP in BOARD bar |
| Network facts (SSID, gateway, board address, upstream DNS, host) | M | Board panel, now shown locked and unlocked (was locked only) |
| CPU two-minute chart | K | |
| Web canvas | M | replaced by the 3D map (section 6) |
| Hover tooltip `#tip` | K | |

## 4. Controls and calls
| Item | S | Where / why |
|---|---|---|
| Brand title / `P` | K | |
| Login sheet | K | |
| Status pill (Live, DNS off, Demo data, Lost contact) | K | tag with shape glyph |
| Encrypted / Not encrypted tag | K | |
| Slowed tag | K | |
| Refused button + sheet (IP list, `ALLOW_EXTRA` command, Copy) | K | |
| Speed test: gauge, phases, stats, verdict, Start/Stop/Close, history (30, `overheard.speed`), note | K | gauge uses the accent ramp |
| LED sheet: characters, brightness, level text, 140 ms tick | K | dots use the accent colour (were fixed blue) |
| Profiles sheet: chips, weekly heat, shares, Download vector | K | |
| Flagged sheet: list, summary, Copy list | K | |
| "Slow down flagged devices" switch, `POST /api/settings {slowdown}` | M | Devices panel (admin row); sheet points to it |
| Skin pill / `S` (admin) | M | Look button opens a picker of all 48; `S`/`Shift+S` still cycle |
| Theme pill toggles light/dark only on Classic | M | now toggles mode on every skin (the R16 jump-to-Classic quirk is gone) |
| Lock pill | M | see above |
| Device focus (map node, matrix header, lookup chip, new Devices list) dims others, filters lookups | K | |
| Sheets close by scrim, X, `Esc`; focus moves to first control | K | |

## 5. Polling and timers
| Item | S | Where / why |
|---|---|---|
| `GET /api/stats` every 1 s after the previous ends, 4 s timeout | K | |
| Web canvas redraw rAF ~30 fps | N | replaced: map draws only on data, drag or a moving pulse; zero frames idle or hidden (tested) |
| Speed gauge rAF while sheet open; 200 ms sampling | K | also stops when the tab is hidden |
| LED tile animation 140 ms | K | skips while hidden |
| Copy label reset 1.5 s | K | |
| Resize re-render | K | |

## 6. The node web (now the 3D map)
| Item | S | Where / why |
|---|---|---|
| Board in the centre with host name | K | |
| Devices on the sides, most recently active, max 3..10 | M | max 12 (8 on phones), rest summarised |
| Node radius by sqrt(rate) | N | node size is fixed (minimum scale enforced); rate shows in the pulses and label |
| One colour per device in sorted-id order | M | accent hue plus offsets, plus a glyph per kind and the name |
| Label (name, dedupe suffix) and sub line ("Now: ..." admin, else lookups) | M | sub line shows LIVE/IDLE + service (admin) or lookups; drops when crowded |
| "+N more, quieter", "N devices seen", empty state | K | |
| Edges, thicker and coloured when live | M | rails light up on real pulses; live/idle is in the label |
| Two travelling dots per live line | N | replaced by pulses from real events |
| The way out: archway, heavy line scaled by log10(rx+tx) | N | Internet node and a rail; line width no longer scales with traffic |
| Way-out label: SSID / Wi-Fi / Wired / Internet, "gateway X" | M | Internet node: "<network> . gw <gateway>" |
| Gate and device tooltips | K | |
| Hover cursor, click node = focus, focus ring | K | pressed-in node |
| Narrow (< 560 px) smaller sizes | M | still projection, drag rotates |
| Canvas aria-label only | M | now a hidden text list of nodes and states |
| Blocked queries not drawn (counts only) | M | new: pulses, blocked ones stop at the board ring |

## 7. Skins
| Item | S | Where / why |
|---|---|---|
| 48 skin names | K | |
| `applySkin`, `?skin=`, `overheard.skin` | K | `?mode=` added for screenshots |
| `overheard.theme` | M | now the global dark/light mode |
| Hand-set colour tokens per skin | N | one 4-number palette per skin; 96 skins by formula, contrast tested |
| Per-skin radius, border width, fonts, glass blur, gradients | N | geometry is shared by all skins by design |
| Per-skin heat ramp, fixed 8-colour device palette | N | derived from the accent |
| `skins.css` / `skins.js` | M | no longer loaded by the page; still served (a test requests `/skins.js`) and read by two dev tools |

## 8. Figures for the two bars
| Item | S | Where / why |
|---|---|---|
| CPU % (+ pips) | K | BOARD bar |
| Memory used/total | K | BOARD bar |
| Disk used/total | K | BOARD bar |
| Temperature | K | BOARD bar |
| Uptime | K | BOARD bar |
| Download Mbps (+ pips) | K | NET bar |
| Upload Mbps | K | NET bar |
| Network name | K | NET bar |
| Gateway | K | NET bar |
| Board address | K | NET bar |
| Upstream DNS state | K | NET bar |
| Devices online | K | NET bar (DEV) |
| Latency not live; load/cores unused | K | not shown |

## 9. Risks listed
| Item | S | Where / why |
|---|---|---|
| 3D map is a rewrite; pulses need events | M | counter deltas between polls, attributed to devices with new activity (estimate), no server change |
| Blocked-vs-allowed per device | M | same estimate, from the "Ads and trackers" lane |
| Canvas colours read from tokens | K | |
| Device colours backed by glyph | K | |
| Skin and mode independent | K | |
| `/3ds` untouched | K | |
| Speed test goes to Cloudflare | K | |
| Hero fit loop | N | see section 3 |
| localStorage keys kept | K | |
| Esc chain | K | |

**Totals: kept 59, moved 35, not carried 12 (106 rows).**
