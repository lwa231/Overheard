# Overheard r16 dashboard: feature inventory (nothing may be lost)

Source read: `unoq-netmon.r16/src/overheard/web/index.html` (775 lines, 70 KB, one file: CSS + HTML + JS), `skins.css` (47 skin blocks), `skins.js` (48-entry registry + `applySkin`), `3ds.html`, `server.py`, `stats.py`, `sysinfo.py`. Served by `server.py`; only `/`, `/3ds`, `/skins.css`, `/skins.js` are static (whitelist). Everything else is `/api/*`.

## 1. Access model (locked vs unlocked)

The server decides: `/api/stats` returns `unlocked` and, when locked (`build_stats(full=False)`), already omits domains. The page also runs `scrub()` as a second guard (empties `recent`, `adult`, `settings`, `conns`, `now`, per-device `evidence`/`now`, drops "Adult content" rows).

| Aspect | Locked (default) | Unlocked (admin) |
|---|---|---|
| Unlock | Click brand title "Overheard" or press `P` -> login sheet -> `POST /api/unlock {secret}` (cookie session; 429 + `Retry-After` shown as text) | Same gesture or Lock pill -> `POST /api/lock {}` |
| Hero | Always "Quiet." + "Protection active/off" + "N blocked so far" | Shows current service ("Video.") + mode (Playing video/audio, Searching, Browsing) + up to 3 evidence domains |
| Latest lookups card (`#midLookups`) | hidden | shown: domain (sub dim, registrable bold), device dot+name (click = focus), blocked tag or service, strike-through if blocked, "Flagged" button, tally, "Show all" |
| Pills hidden when locked | Profiles, Skin ("Change look"), Lock | visible |
| Pills always visible | Status, Encrypted/Not encrypted, Refused N (when any in last hour), Speed test, LED matrix, theme (sun/moon) | same + Slowed N |
| Device tooltips | label + confidence only | + "Seen asking for"/"Signs of" evidence list |
| Keys | `P` toggle login | `P` lock, `S` / `Shift+S` next/prev skin, `Esc` closes topmost sheet |
| `/api/flagged`, `/api/profile*` | 403 locked | allowed |
| `/api/settings` POST | 403 | allowed (only `slowdown`) |
| Unlock-gated skin switching | skin button/keys do nothing | works |

Note: LED (`/api/led`, `/api/sprites`) is NOT gated; anyone can change LED character/brightness. Keep or consciously gate in r17.

## 2. Layout (current)

Three-column CSS grid, `overflow:hidden`, full viewport: left (hero, 3 tiles, traffic matrix) | middle 286 px (Latest lookups when unlocked, Board card) | right (web canvas). At `<=1000px` becomes one scrolling column ordered: hero, tiles, web (70vh), lookups, board. Breakpoints 1250, 1000, 560. Cards: radius 26, 1 px border.

## 3. Views, panels, figures

| Panel | Figures / content | Data source |
|---|---|---|
| Brand row | "Overheard" (click = unlock); pills (see section 4) | `dns`, `net`, `refused`, `adult.slowed` |
| Hero `#h` + `#why` | headline (fit-to-width loop, min 24 px), why line, small line | `now` (unlocked), `dns.enabled`, `dns.blocked` |
| Tile Blocked | count, % of lookups, sparkline (last 10 min, 40 bins of 15 s, rows service "Ads and trackers") | `dns.blocked`, `dns.total`, `devices[].rows[].v` |
| Tile Lookups | total, "N device(s)", sparkline of all rows | `dns.total`, `dns.clients` |
| Tile Download | Mbps (2/1/0 decimals by size), tooltip "Upload X Mbps", sparkline from 90 client-side samples (1/s) | `rx`, `tx` |
| Traffic matrix (canvas `#c`) | per device header (dot, name, live/idle, address, lookup count) + up to 4 service lanes of 120 x 5 s heat cells (10 min), "Connection" speed lane for the board, axis (10 min ago / 5 min / now), low-high legend, hover cell tooltip ("Device, service, 35 s ago: N weighted lookups"), hover header = device tooltip, click header = focus device | `devices[]` `{id,label,confidence,last,lookups,rate,rows[{service,line?,v[120]}],evidence,now,shared}`, `t0`, `step` (5), heat ramp |
| Latest lookups (admin) | see section 1; shows up to 3..N rows by height, 8 on mobile | `recent[24]` |
| Board card | meters CPU %, Memory used/total GB, Disk used/total GB, Temp C (scale 20-90 C); "Up 3d 4h"; facts (locked only!): Network (SSID or Wi-Fi/Wired), Gateway, Board address, Upstream DNS state, Host; CPU line chart (60 samples, ~2 min) | `sys{cpu,mem_*,disk_*,temp,uptime,cpu_hist[60]}`, `net{ssid,iface,wireless,gateway,addr}`, `host` |
| Web (canvas `#web`) | see section 6 | `devices`, `net`, `rx`+`tx`, `host` |
| Tooltip `#tip` | device (label, confidence text, evidence, address) and gateway (name, gateway, board address/iface) | |

Meters turn "hot" (ink colour) above 85 %. Facts block shows only when locked (`body:not(.unl) .facts`).

## 4. Controls and calls

| Control | Where | Action | API |
|---|---|---|---|
| Brand title / `P` | brand | open login or lock | `POST /api/unlock {secret}`, `POST /api/lock {}` |
| Login sheet | modal | secret field, Cancel, Log in; errors: empty, 429 wait, wrong, unreachable | `POST /api/unlock` |
| Status pill | brand | Live / DNS off / Demo data / "Lost contact with the board" (bad) | `GET /api/stats` result |
| Encrypted pill | brand | tls = Encrypted (lock), plain/mixed = "Not encrypted" (warn), idle = hidden | `dns.upstream` |
| Slowed pill | brand | "N devices slowed", title lists seconds left | `adult.slowed` (admin + slowdown on) |
| Refused pill -> Refused sheet | brand | list of IPs (count, ago), copy-able command `ALLOW_EXTRA=ip/32,... bash scripts/install.sh`, Copy command | `refused[12]` |
| Speed test pill -> Speed sheet | brand | gauge (log-ticks 0-1000 Mbps, canvas, animated needle), phases latency/down/up (7 s + 6 s), stats Mbps down/up, ms latency, verdict, Start/Stop/Close, history of 30 in `localStorage overheard.speed`, note ~100 MB | browser-side to `https://speed.cloudflare.com/__down`, `/__up` (not the board) |
| LED pill -> LED sheet | brand | grid of characters (animated canvas tiles, sit when quiet, run when busy), brightness slider 10-255, level text (quiet/light/busy/very busy), 140 ms tick | `GET /api/sprites`, `GET /api/led`, `POST /api/led {character}` / `{brightness}` |
| Profiles pill -> Profiles sheet (admin) | brand | device chips, category chips, weekly heat (7 days x 24 h, local time), category share bars, "Download vector" (`profile.json`), message when none | `GET /api/profiles`, `GET /api/profile?id=` |
| Flagged button -> Flagged sheet (admin) | Latest lookups header | list domain, hits, ago; "Slow down flagged devices" switch; summary; Copy list | `GET /api/flagged`, `POST /api/settings {slowdown}` |
| Skin pill / `S` (admin) | brand | next skin; label shows name | none (local) |
| Theme pill (sun/moon) | brand | toggles light/dark ONLY on Classic; on any other skin it jumps back to Classic | none (local) |
| Lock pill (admin) | brand | lock | `POST /api/lock` |
| Device focus | web node, matrix header, lookup device chip | dims others to 28 %, filters lookups, "Show all" | local |
| Sheets | all | click scrim or X or `Esc` closes; focus moved to first control | |

Not present: any settings page, any block/allow-list editor, any DNS-off toggle.

## 5. Polling and timers

| What | Interval |
|---|---|
| `GET /api/stats` (timeout 4 s, `credentials:same-origin`) | 1 s after previous finishes (`tick`) |
| Web canvas redraw | rAF, throttled to ~30 fps, skipped when `document.hidden`; not started at all if reduced motion |
| Speed gauge | rAF while sheet open; meter sampling every 200 ms |
| LED tile animation | `setInterval` 140 ms while sheet open |
| Copy button label reset | 1.5 s |
| Resize | full re-render |

Stats are rendered on every poll (no diffing except cached `_h` strings). Everything is canvas except pills/tiles/lists.

## 6. The node "web" (right card, canvas 2D)

Drawn by `drawWeb(t)` + `drawGate`. No library. Layout is computed per frame from canvas size.
- Centre: **this board** (accent disc r=23, chip glyph, soft pulsing halo, host name above).
- Right: devices (max 3..10 by height, the most recently active, sorted by id), placed on a half-ellipse (`cx + rx*sqrt(1-s^2)`, `cy + ry*s`), radius 8..17 by `sqrt(rate)`, one colour per device from an 8-colour palette assigned in sorted-id order (`dcol`). Label (name, dedupe suffix with last address part) + sub ("Now: ..." admin, else "N lookups"); sub drops when crowded. "+N more, quieter" and "N devices seen" captions; empty state text.
- Edges: quadratic curve board->device, coloured and thicker when live (last seen < 30 s), faint when idle; two travelling dots per live line.
- Left: **the way out**: a drawn archway "door" with an arrow, a heavy accent line whose width scales with `log10(rx+tx)`, travelling dots when traffic; label = SSID / Wi-Fi / Wired network / Internet, sub "gateway X" / "the way out". Tooltip with gateway + board address.
- Hover: pointer cursor + tooltip on node or gate; click node = focus. Focused node gets ring.
- Data: `S.devices[]` (id, label, last, rate, lookups, now), `S.net`, `S.rx+S.tx`, `S.host`. Blocked queries are NOT drawn at all today (only counts); r17 needs per-event data (see section 9).
- Narrow (<560 px): smaller radii/labels.
- Accessibility today: canvas `aria-label` only; no text equivalent of the map.

## 7. Skins (current system)

- `skins.js`: array of **48** `{id,name,scheme:'dark'|'light',ramp?}`; `applySkin(id)` sets `<html data-skin>`, `<html data-theme>` (= scheme; for "classic" = saved `overheard.theme` or dark), `window.SKIN_RAMP`, saves `overheard.skin`. Initial id: `?skin=` query, else localStorage, else classic.
- `skins.css`: 47 hand-written `:root[data-skin=X]{...}` blocks (classic lives in index.html, with a separate `[data-theme=dark]` block). Each block hand-sets: `--paper --card --well --accent --accent-ink --accent-rgb --ink --ink-2 --rule --line --edge --ads --grid --scrim` plus shape tokens `--r` (radius 0-40), `--bw` (border width), `--shadow`, `--display`/`--text` fonts, sometimes `--bg` (gradients) and `--blur` (glass). ~14 colour tokens + 6 shape tokens each, ~500 bytes.
- Heat ramp: `ramp` array of 4-6 `[stop,[r,g,b]]` per skin; default `RAMP0` rainbow. Canvas code reads CSS vars once via `theme()` (INK, INK2, WELL, PAPER(=--card), ADS, ACC(=--accent-ink), ACCRGB, GRID) and recomputes `--on-accent` (black/white by luminance .18).
- Device colours `DPAL` are fixed, same on every skin.
- **Light/dark today:** every skin is single-mode (20 light, 28 dark incl. Classic, by `scheme`). Only Classic has both. The theme button on any other skin silently switches to Classic (and relabels "Classic"), so a user on "Rose" cannot get a dark Rose. 96 consistent skins therefore do not exist; there is no formula, every value is hand-picked, and contrast was never checked per skin (e.g. `--ink-2` alphas .58-.72 on tinted cards). Accent is used both as fill and as text (`--accent-ink` patches this per skin).
- Other quirks: tokens `--rule/--line/--edge` mix hex and rgba; `--ads` is a bare "r,g,b" triple used only by canvas; `--on-accent` is set from JS; glass skins (aurora, aero) rely on `backdrop-filter`.
- Skin names (47+classic): classic paper terminal brutal signal aurora mint amber violet lime sand ice dots panel linear crt rings stripe slate ember oxide plum cobalt graphite moss dusk neon ocean rose citrus sky lavender ledger blueprint chalk coral mono-light olive sunrise steel toxic copper glacier candy noir pixel zen aero. (Several are named after products/styles: rename in r17.)

## 8. Performance and network figures available (for the two readout bars)

Already on the dashboard (use only these):

| Bar | Figure | Today shown as | Field |
|---|---|---|---|
| Board | CPU % | meter + 2-min line | `sys.cpu`, `sys.cpu_hist[60]` |
| Board | Memory used / total GB | meter | `sys.mem_used/mem_total` |
| Board | Disk used / total GB | meter | `sys.disk_used/disk_total` |
| Board | Temperature C | meter (20-90 scale) | `sys.temp` |
| Board | Uptime | "Up 3d 4h" | `sys.uptime` or `uptime` |
| Network | Download Mbps | tile | `rx` (bytes/s) |
| Network | Upload Mbps | tile tooltip only | `tx` |
| Network | Network name (SSID or Wi-Fi/Wired) | board facts (locked) | `net.ssid/iface/wireless` |
| Network | Gateway address | facts + gate tooltip | `net.gateway` |
| Network | Board address | facts + gate tooltip | `net.addr` |
| Network | Upstream DNS: Encrypted / Not encrypted / Partly / Demo / Idle | pill + facts | `dns.upstream` |
| Network | Devices online | tile sub-label | `dns.clients` |
| Network | Latency | speed test only (ms, not live) | not live; do not show |

In the API but NOT shown today (avoid unless the owner agrees): `sys.load`, `sys.cores`.

## 9. Hard-to-carry-over items and risks

1. All visuals are 2D canvas with per-frame layout in JS; the 3D-parallax map is a rewrite, not a restyle. Per-event pulses (blocked stops at the board) need event data: the locked `/api/stats` has no per-event feed. Cheapest honest option: derive pulses from change in `dns.total/blocked` and per-device `lookups` deltas between polls (no domains), or add a locked `events` array of `{client,blocked,t}`.
2. Blocked-vs-allowed per device is only in the unlocked `recent` list today.
3. Heat-ramp canvas matrix, speed gauge, profile heat and LED sprite canvases read theme colours from JS (`theme()`); a formula-driven skin system must expose the same values (accent rgb triple, ink, well, grid) or the canvases must read computed styles.
4. Fixed 8-colour device palette must be derived from the accent hue and backed by glyph/shape, not colour alone.
5. Theme button / `skins.js` relationship (see section 7) must be redone: skin id and mode become two independent settings.
6. `3ds.html` (separate 183-line legacy PIN page, own XHR calls to `/api/unlock`, `/api/stats`, `/api/settings`, `/api/lock`) is untouched by the redesign unless the owner says otherwise.
7. Speed test talks to Cloudflare from the browser (needs internet DNS via the board; ~100 MB).
8. Hero text auto-fit loop and canvas text measurement depend on fonts; with system-font-only this is stable.
9. `localStorage` keys: `overheard.theme`, `overheard.skin`, `overheard.speed`. Keep them (or migrate) so existing users keep history.
10. `Esc` handler is a hand-written chain over 7 sheets; keep the "close topmost" behaviour.
