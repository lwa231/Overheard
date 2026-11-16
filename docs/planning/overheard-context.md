# Overheard (AWL) — context for the next session (2026-11-11)
Merged from project docs `overheard-r16-plan`, `overheard-r16-addendum`, `overheard-handoff`, `overheard-r15-notes`. Code: `unoq-netmon.r16/` (R16.1, 231 tests, lint + smoke green in CI). Build handoff: `../HANDOFF.md`.

## What it is
Stdlib-only Python DNS ad blocker + network monitor + token-gated dashboard on an Arduino UNO Q (`arduino@100.69.41.76`, UnoQ1). DoT upstream 1.1.1.1:853 with ~1.5 s fallback to plain UDP and a 60 s breaker; allow-list plus `--allow-extra`; hard-coded adult guard; SafeSearch rewrite; fingerprinting; SQLite profile DB (16 MB cap); 48 skins; speed test.

## R16 decisions (locked)
- D1 adult guard on, hard-coded, hidden; only very explicit matches (exact `xxx`/`porn`/`porno` label, explicit brands, blocklist hits). YouTube never flagged.
- D2 slowdown: persisted toggle, default off, changeable only when unlocked; never affects blocking.
- D3 ad-stream DPI parked in `experimental/`.
- D4 `/3ds` page: ES5, XHR polling, no flex/grid, 320 px column (top 240 px status, bottom keypad). Untested on the real console.
- D5 server-side lock: `POST /api/unlock {secret}` → cookie `ovu` (30 min, 5 failures/min then 429); `/api/lock`; `/api/settings {slowdown}` needs unlock. Locked `/api/stats` carries no domains. Secret file `~/netmon/data/unlock`. Doctor exception: loopback + `ov` cookie + `X-Overheard-Doctor: 1`.
- D6 DoT default with fast fallback. D7 no public range in code; installer keeps previous extras, adds the Mac's address, `ALLOW_EXTRA=none` clears. D8 YouTube Restricted removed.

## Status
- Install, Check passed on the board: service active, dashboard up, DNS answers, `doubleclick.net` → 0.0.0.0, upstream DoT. The board sees the Mac as 203.0.113.240 (building NAT, shared public range 203.0.113.0/24).
- Phone Test: `last-phone-test.txt` contains only a timestamp, no verdict. Unresolved.
- Not hardware-tested: `/3ds` on the console, `make_profile.py` Apple profile, Android, Tailscale path.

## Auto-DNS lanes
- A: own router/travel AP, DHCP option 6 = board (recommended if the user owns a router; GL.iNet ~$30).
- B: Apple `.mobileconfig` — iOS profiles cannot set plain-IP DNS (only DoH/DoT), so manual steps until the board serves DoT with a valid cert.
- D: Tailscale global nameserver + Override local DNS (needs the app on each device; fixes the shared-NAT per-device problem). Unconfirmed whether Tailscale is installed (`tailscale status`).
- Never rogue DHCP or ARP spoof the shared building network.
- Limits: iCloud Private Relay and DoH apps bypass DNS; client isolation may block reaching the board.

## Queue
Phone Test diagnosis; UI revamp (user is sending references; tokens → components → dashboard → 3DS → iOS); hardening (fuzz `dnsproto`, auth/Host abuse, unlock brute force); iOS dashboard (Safari Add to Home Screen over Tailscale HTTPS vs native app); Alexa preset toggles; traffic decryption on own devices (plan only); Hostinger VPS exit node 198.51.100.10; second board ML from profile DB; GitHub push prep; cleanup of r15 and Gemini scripts on the user's "clean up".

## R17 UI revamp (user decisions 2026-11-12)
- BUILT 2026-11-12 in `unoq-netmon.r17/` (page: `src/overheard/web/index.html`; checklist `UI-CHECKLIST.md`; design + mock in `unoq-netmon.r17-design/`). Appearance/layout only, no Python changed; 235 tests pass (1 known Pillow failure, same on r16); fresh security audit: 4 low findings, fixed. Tested against demo data only: NOT yet run on the board, on a real phone, or with 30+ devices. r16 untouched (rollback = r16's installer). 12 old visual behaviours not carried over (see checklist). Open: should app-category labels stay visible when locked?
- Appearance only: every current feature and figure stays. Game-like: raised/3D controls, HUD chrome, dark with glow; original design in the spirit of the user's reference screenshots, drawn in code (no image assets). Silent for now.
- Main view: node map like the current web, possibly with 3D-style depth on desktop; motion only when traffic happens, paused when hidden/asleep or idle, reduced on phones and with reduce-motion. One interface for all screens.
- Locked (default) state shows the map, animation and performance bars, no domains. Admin (unlocked) adds extras, including a live per-profile traffic feed.
- Two small readout bars (board performance, network), compact like a game's frame-rate overlay, using data the dashboard already has.
- Skins: 48 themes, each with a dark and a light mode (96), from one palette per theme with generated depth shading (proposed, to confirm).
- 3DS (New 3DS XL, RED-001), after the dashboard revamp: simplified dashboard; top screen = map/status with the small bars along the bottom; touch screen = command buttons; unlock with the on-screen 9-digit pad (same code); one dark and one light mode; goes dark when the console sleeps or is closed.
- 3DS app references supplied by the user (known-good homebrew apps; not yet read; use for structure and ideas, copy no code without checking the licence): https://github.com/skrimby1/controlmole-3ds , https://github.com/kylie-grace/homepad-3ds , https://github.com/Just-a-Spider/SysMon
- Stays in the local Overheard folder (no GitHub). Build the visual layer so it can be copied into the agency repo later. Skill for UI work: `ui-ux-pro-max`.

## Honest limits
DNS cannot throttle open connections; the guard only affects devices using the board for DNS; behind NAT many devices share one address; nothing is 100% secure.

## Tool quirks
Sandbox and the laptop VM cannot reach the board; all board steps are the user's double-clicks. Package with `tar --exclude='*.tgz' -czf`; unpack on the laptop with `tar xzf` (keeps exec bits; `sed -i` can drop them). `web/index.html` has very long lines: patch by exact-string replace.
