# Overheard R16 handoff

## What R16 is
Overheard is a DNS ad blocker and live network monitor for the Arduino UNO Q (Python, no dependencies,
DNS on port 53, dashboard on port 8080, LED character on the matrix). R16 is the cleaned-up and hardened
version of Gemini's r15, produced by six workers and checked by an independent audit. Everything is
committed as "R16". CI: ruff clean, sprite check ok, 173 tests pass, end-to-end smoke test ok.

## What changed versus Gemini's r15
- Stealth lock, enforced by the server: the dashboard starts locked and shows no looked-up names; press P to
  lock or unlock. Unlock trades a secret (`data/unlock`, shown by Check Overheard.command) for a 30-minute
  server-side session. Five wrong tries per minute per address, then 429. Constant-time comparison.
- Adult guard: fixed in code, blocking has no flag, setting, env var, file or API that can weaken it.
  YouTube is never flagged. Big first-party hosts only switch off the name heuristics.
- Slowdown is now an optional, persisted toggle (default off, unlocked only). Blocking is identical on or off.
- DoT upstream by default with a fast plain-UDP fallback (1.5 s connect limit, retry DoT every 60 s).
  The r15 default of NO_TLS=1 is gone; NO_TLS=1 is opt-in only.
- No public IP ranges in code defaults (r15 hard-coded a /24). Installer keeps earlier extras,
  adds this Mac automatically if outside the default ranges, ALLOW_EXTRA=none clears all.
- YouTube Restricted Mode removed everywhere. Mac, iPhone and iPad share one label, "Apple device".
- adstream.py, live_capture.py and the other unreviewed r15 code moved to `experimental/`: not imported by
  `src/`, not in the shipped package (a test checks both).
- New: `Phone Test.command` plus `overheard.doctor` (did the phone's lookup arrive, get refused, or get answered).
- New: `src/overheard/web/3ds.html` served at `/3ds` (placeholder, see next session).
- Fixes: scripts/shots.py and skin_shots.py unlock first (LOCKED=1 skips the profiles shot); status.sh reports
  upstream mode and the unlock secret; README has an R16 section; docs/r16-audit.md lists what was wrong in r15.

## Install, check, phone test (on the Mac, in `unoq-netmon.r16`)
1. Double-click `Install Overheard.command`. It sends the program to the board, installs the service
   (board sudo password once) and runs a check.
2. Double-click `Check Overheard.command`. It shows: service state, the board's real address, allowed
   networks, DoT or plain upstream, DNS answers, ad blocking, and the unlock secret. Saved to
   `~/Desktop/ArduinoQ/last-check.txt`.
3. Set the phone's Wi-Fi DNS to Manual with the board's address. Double-click `Phone Test.command`, open
   `http://phonetest.example.com` on the phone within 90 s. Result is saved to `last-phone-test.txt`.
   "Refused" prints the exact ALLOW_EXTRA line to re-run the installer with.
4. Dashboard: `http://<board>:8080/?key=<token>` (token in `~/netmon/data/token` on the board).
   Press P and enter the unlock secret to see names, the Filters sheet and the slowdown switch.

## Decisions
- D1: Adult guard cannot be disabled or weakened by any flag, env var, setting, file or HTTP endpoint.
- D2: Slowdown is a persisted toggle, default off, changeable only when unlocked; blocking is identical on or off.
- D3: `experimental/` is never imported by `src/` and never shipped in the board package.
- D4: 3DS: a `/3ds` dual-screen web page (served as a placeholder in R16, not built yet); native homebrew stays a plan.
- D5: The lock is server-side: locked responses carry no looked-up domain, no client storage flag, unlock is rate-limited and constant-time.
- D6: DoT is the default with fast UDP fallback; plain-only is opt-in (NO_TLS=1) and reported by status.sh.
- D7: No public IP ranges in defaults; extras are kept across installs, ALLOW_EXTRA=none clears them.
- D8: YouTube is never flagged, YouTube Restricted is gone, Apple devices have one label.

## NOT hardware-tested
Everything board-side: the installer and systemd service, port 53 and DoT from the board, the LED matrix app,
Phone Test on a real phone, the dashboard served from the board, sysinfo and connection polling on the
board's Linux. CI and the smoke test run on a Linux dev machine against local sockets only.

## Next session plan
1. 3DS dual-screen page at `/3ds`: ES5 only, XHR (no fetch, no modules), two layouts, top screen 400x240 and
   bottom screen 320x240. Read `docs/3ds_admin_dashboard_plan.md` first. Must obey the same server-side lock.
2. Hardening: run the board-side checks above, fix whatever the real board shows; review
   the dashboard's plain-HTTP exposure (see docs/security.md, Tailscale serve).
3. Plan docs: update docs/app-plan.md and the 3DS plan to match R16.
