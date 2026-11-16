# HANDOFF — everything about this project (2026-11-16)
Read this first, then `docs/planning/START-HERE.md`. Written for any Claude session (or person) picking this up cold. No secrets are in this repo. Public addresses were replaced with documentation addresses (203.0.113.x, 198.51.100.x).

## Contents
1. The owner and how to work with him
2. Operating model (orchestrator + workers)
3. Overheard: what it is and its state (build r17)
4. Decisions that are locked
5. Network, Tailscale and VPS
6. LED matrix
7. Agency project (separate, local server)
8. Economics and guardrails
9. Repo map
10. Tested vs untested
11. Open questions and next steps
12. Lessons and tool quirks

## 1. The owner and how to work with him
- Time zone America/New_York, Mac user (`luqman_ahmed`), GitHub `lwa231`. Hardware: Arduino UNO Q "UnoQ1" running Overheard, a second UNO Q, a Nintendo 3DS XL, a Hostinger VPS, a local Ubuntu server being built (Ryzen 5 7600X, 16 GB DDR5), a Windows PC, an iPhone, a MacBook.
- Style: terse, calm replies; exact copy-paste commands; minimal laptop interaction (double-click `.command` files, results written to files Claude reads: `last-check.txt`, `last-phone-test.txt`, `last-led-install.txt`).
- Dictates by voice, so messages are long and loose; extract the intent, do not argue with the grammar. Humour welcome, profanity occasional.
- Once told "ready/go", keep going and do not ask again. Do not launch work into a known usage limit; schedule a restart after the reset. Ask questions in one batch.
- UI taste: distinctive, not generic AI-looking; dark default; Hostinger-style cards (soft rounded cards, stat tiles with sparklines, pill badges, one accent) and Google speed-test gauge. Skills for "Be Terse" and a UI/UX skill exist on his Mac.
- Never suggest demo mode (kept in code for tests only). Keep only the newest build on the laptop; delete old builds only on his "clean up". Never touch `archive/unoq-netmon.old` (his original code). Stay inside `~/Desktop/ArduinoQ`. Ask before sudo.
- Content filters (adult guard) are hard-coded and not disableable by anyone; the slowdown is a separate toggle.
- Honesty: label anything not tested on hardware; targets are not forecasts; when wrong, say so and fix.

## 2. Operating model
- Main model (Fable, medium effort) = orchestrator only: thinks, plans, briefs, audits, talks to the user, writes no project code.
- Sonnet 5.5, high effort = all hands-on work. An independent auditor worker (fresh context) never audits its own code. One finisher commits and packages; parallel workers never commit.
- Brief format: MAIN IDEA / files owned / off-limits / CRITERIA (definition of done incl. tests) / decisions already made / REPORT with a word cap. Reports say what was NOT verified.
- Waves: 3-5 workers in parallel on disjoint files, an integration worker fixes seams, `make ci` green, commit, package, checkpoint. View screenshots of any UI before calling it done.
- Usage discipline: check remaining usage before a wave. The 2 a.m. launch hit a limit and wasted a run. Keep replies short.

## 3. Overheard (AWL)
Stdlib-only Python DNS ad blocker and network monitor with a token-gated dashboard, running as a systemd service on the Arduino UNO Q.
- DNS: blocklist (~78k domains), DoT upstream (1.1.1.1:853) with ~1.5 s fallback to plain UDP and a 60 s circuit breaker, per-client rate limit, allow-list plus `--allow-extra`, SafeSearch rewrite, TTL cap, strict parsing.
- Adult guard: hard-coded, hidden, tuned to very explicit matches only (exact `xxx`/`porn`/`porno` label, explicit brands, blocklist hits). YouTube is never flagged. Slowdown (8 s per query for the offending address) is a persisted toggle, default off, changeable only when unlocked.
- Server-side lock: locked dashboard shows "Quiet."; no domains leave the board while locked. `POST /api/unlock {secret}` sets cookie `ovu` (30-min session, 5 failures/min per address then 429); `/api/lock`; `/api/settings`. The access key (`?key=`, cookie `ov`) is separate. Unlock secret file: `~/netmon/data/unlock` on the board; access key: `~/netmon/data/token`. Never commit either.
- Fingerprinting by looked-up names, SQLite profile DB (16 MB cap), 48 skins, speed test (Google-style gauge), board vitals, topology with gateway doorway, refused-sources pill, hover cards.
- `/3ds` page: ES5, XHR polling, 320 px column (240 px status, touch keypad). Not tested on a real console.
- Builds: r14 (original look and quality) -> r15 (Gemini/AntiGravity edits that broke things: blank dashboard from syntax errors, fake client-side login, leaking `/api/stats`, plaintext upstream default, dead DPI code) -> r16 (rebuilt and audited, `archive/unoq-netmon.r16`, docs/r16-audit.md) -> r17 (current, repo root: LED animation skins, install scripts, UI checklist, design work). `archive/unoq-netmon.r17-design` is the design exploration.
- Install on the board: double-click `Install Overheard.command`, then `Check Overheard.command` (writes `last-check.txt`, prints Tailscale status), `Phone Test.command` (writes `last-phone-test.txt`). The Mac app `launcher/Overheard.app` opens the dashboard (it fetches the key over SSH).
- Status reported by the user: running for days, "very smooth", phone and Mac using it as DNS; speed test about 188 down / 122 up while using only the board's DNS.

## 4. Decisions locked
D1 guard hard-coded and hidden. D2 slowdown toggle. D3 ad-stream DPI parked in `experimental/`. D4 3DS page built, untested on console. D5 lock is server-side. D6 DoT default with fast fallback. D7 no public range in code; installer keeps previous extras, adds the Mac as the board sees it, `ALLOW_EXTRA=none` clears. D8 YouTube never flagged, YouTube Restricted removed.

## 5. Network, Tailscale and VPS
- The building shares one NAT; all the user's devices look like one public address to the board. The board's building address is not the one to use for DNS from outside; use its Tailscale address.
- Tailscale (GitHub login, free plan): all devices joined — the board (`unoq1`, 100.107.57.35), the local server (`awlserver`, 100.124.220.78), the VPS (100.119.85.78), Mac, iPhone, Windows PC. Tailscale sees metadata only (who is online), not traffic or DNS lookups. Turn on two-factor on the GitHub account; consider Tailnet Lock; Headscale on the VPS is the fallback if metadata is a concern.
- DNS from anywhere: set each device's DNS to the board's Tailscale address (or the Tailscale admin console global nameserver with Override local DNS). Commands for Mac, Ubuntu (systemd-resolved) and Windows (PowerShell) were given in chat; the Mac one is `sudo networksetup -setdnsservers Wi-Fi <ip>`, undo `... empty`.
- VPS (Hostinger, Ubuntu with Docker): Tailscale installed and advertised as an exit node (worked; speeds about the same). Repo `lwa231/AWL_Overheard_VPSVPN` (private) holds `vps/bootstrap.sh` and `vps/harden.sh` (ufw). NOT YET DONE: the firewall (user typed lowercase `yes`; it needs `YES`), `docker ps` check (Docker can bypass ufw), SSH over Tailscale test, reboot for a pending kernel update, move off root login. Agency code and files never live on the VPS.
- Placement (hard): Overheard stays on the Arduino. The agency lives only on the local Ubuntu server. The VPS only relays (VPN exit, later a messaging relay). The Mac only SSHes into the server. A small API links Overheard and the agency. See `docs/planning/agency-network.md`.
- Planned "Gate": a separate program that drives an nftables firewall using Overheard's DNS (allow a device to connect only to addresses it recently resolved); exit node on the board is possible but the board is small, Wi-Fi only, and a single point of failure; start with the server's outbound traffic. Messaging between phone, VPS, server and board: no iMessage API exists; plan is a private chat page reachable only over Tailscale, optional self-hosted notifier.
- Auto-DNS lanes: A (own router, DHCP option 6), B (Apple profile; iOS cannot set plain-IP DNS in a profile, so it needs DoH/DoT), D (Tailscale nameserver). Never rogue DHCP or ARP spoof the shared building network.

## 6. LED matrix
- 8x13 matrix on the UNO Q. Characters plus animation skins (matrix, stars, fish, ants, meteor) are baked from `led/sprites/*.txt` and `src/overheard/ledanim.py` by `tools/build_sprites.py` into `sprites.json` and `led/app/sketch/sprites.h`.
- Meteor now shows three meteors per cycle (29 frames).
- The Linux-side app `led/app/python/main.py` polls Overheard at the fixed address `http://172.17.0.1:8080/api/led` (the board as seen from App Lab's container). It failed silently before because `python/token.txt` was never created; `Install LED Sketch.command` now writes it over SSH, and the app prints status lines to App Lab's console. Confirmed working by the user. Upload path: run `Install LED Sketch.command`, import `led/app` into Arduino App Lab, press Run.

## 7. Agency project (see `agency/` and `docs/planning/`)
- A personal "AI agency" on the local Ubuntu server: one boss agent the user talks to; tree Head -> General -> Squad Lead -> Agent (names renameable in one config). Five departments, each with its own instruction directory: research (built first), implementation, marketing, operations, finance/trading.
- Agents exchange information by handoff files with one schema; a tag in the filename says what it is for and which role should use it so others skip it. Kinds: assignment, report, question, answer, data, decision, escalation, plus the planned `returns` kind. Cross-department handoffs go through leads only.
- Compaction (Claude agents only): workers 200k, squad lead 300k, general 400k, boss 500k; local models run uncompacted at their real context.
- Sandbox: per-agent unix user, systemd/bubblewrap, cgroups, nftables network classes, SQLite queue, one shared inference server; process sandbox + git worktree per agent (not V8 isolates, not Kubernetes).
- Scheduling: looping windows with manual toggles; keep the same agents working near each other in time and place like CPU cache (LRU eviction). Sized for one Pro account: 1-3 concurrent agents.
- Dashboard: clone of the Overheard skeleton with chain of command, per-agent metrics, per-agent feed; Business tab (sector cards, returns, runway card, processes table); Office tab (research prototype); 3DS executive dashboard and maybe an iPhone app. Queued: goal dial (user sets a dollar goal for a period; dial above the Live feed that changes colour; process graphs squeezed to the chain-of-command width).
- Built: v0.2 in `agency/` (simulated tree, 119 tests, `make ci`). Not built: goal dial, v0.3 schedule + locality, v0.4 returns + Business tab, UI revamp, 3DS view, a real boss agent.

## 8. Economics and guardrails
- Capital: $150 - $20 = $130 liquid. Two Claude Pro subscriptions ($40/month): one personal and light, one dedicated to the agency. Target $520 profit (floor $500) as a stretch goal, not a forecast. Profit = revenue - $40/month - variable costs. All profit is reinvested (append-only ledger) for about the first 7 months, in this order: Max plan, RAM, GPU. Operations (digital game assets first) leads; finance/trading is small, paper first, live only within a one-time capped budget with broker-side limits.
- Hard guardrails: agents never hold payment methods or funds; every spend, purchase, upgrade, public/outbound action and tax/legal/platform-terms matter needs the user's per-action approval; agents cannot change their own limits, schedules, incentives or instruction files; no evading usage limits; revenue claims need evidence and audit; log every revenue and spend event.
- Local models: no GPU yet, so CPU-only small models; real workers arrive with a GPU (RTX 3060 12 GB researched, or a flashed Radeon Instinct MI25). See `docs/planning/local-models.md`, `usage-estimate.md`.

## 8b. R18 (2026-11-16): configurable board address
`unoq-netmon.r18/` is a copy of r17 where ONLY the board's address changed: it is no longer hard-coded. One file, `board.conf` (BOARD_USER, BOARD_HOST, BOARD_MDNS, SITE), is read by every `.command`, `scripts/*.sh`, the Makefile and `tools/make_profile.py` through `scripts/board.sh`. Several boards: one file per site in `sites/<name>.conf` (`sites/apartment.conf` is today's board, `sites/home.conf.example` is the template) chosen with `SITE=<name>`. Per run: `BOARD_HOST=<address> bash scripts/status.sh`. `launcher/Overheard-launcher.sh` is a Mac launcher that follows the same file. Default is unchanged (the apartment board). New tests: `tests/test_r18_board.py`; full suite 262 pass, the same one browser test still fails as in r17. Plan for two sites (home with the user's own router/modem, apartment, data shared over Tailscale, maybe via the VPS) is `unoq-netmon.r18/docs/multi-site.md`; nothing runs between sites yet. Not run on a real board.

## 9. Repo map
- `unoq-netmon.r18/` = newest build (r17 + configurable board address). Repo root = Overheard r17: `src/overheard/`, `web/` (inside src), `tests/`, `scripts/`, `led/`, `tools/`, `design/`, `branding/`, `dist/` (packaged app and show images), `docs/`, `experimental/`, `*.command` launchers, `Makefile`, `pyproject.toml`, `UI-CHECKLIST.md`.
- `archive/unoq-netmon.old` (original, untouched), `.r15`, `.r16`, `.r17-design`, `archive/gemini/` (Gemini/AntiGravity handoff, 3DS plan and patch scripts).
- `agency/` agency code v0.2. `launcher/Overheard.app` Mac launcher. `docs/planning/` all planning docs and the earlier handoffs.
- Not in the repo: access key, unlock secret, `last-*.txt` result files, the user's personal notes (`trading-bot-ideas.md`, `reel-queue.md`, an unrelated handoff), the `.tgz` packages (duplicates of the folders), and the VPS script repo (`lwa231/AWL_Overheard_VPSVPN`, private).

## 10. Tested vs untested
- Tested in CI: 256 tests pass, 1 browser UI test fails in the sandbox (`tests/test_r17_page.py::test_admin_shows_feed_and_locking_clears_it`: the admin feed is empty in that headless run; investigate first). Agency v0.2: 119 pass.
- Verified on the real board by the user: install, DNS answers, ad blocking, DoT, phone use, LED sketch following the dashboard.
- Never tested on hardware: `/3ds` on a real console; Apple profile; Android; DoT served by the board; Gate; VPS firewall; Linux and Windows DNS commands.

## 11. Open questions and next steps
0. Move to r18 on the laptop (`overheard-r18.tgz` or `unoq-netmon.r18/`), run `Check Overheard.command` from it, then retire r17 on the laptop only on his "clean up".
1. Fix the failing browser test; confirm r17 UI against `UI-CHECKLIST.md`.
2. VPS: `docker ps`, SSH over Tailscale, `sudo bash vps/harden.sh` (type `YES`), reboot, non-root user.
3. Set the Tailscale global nameserver to the board; decide fallback behaviour if the board is down.
4. Phone shortcut / Home Screen icon (icon is `branding/icon-1024.png`); optional iOS home-screen meta tags.
5. Agency: goal dial wave first, then v0.3, v0.4; trading paper-to-live gate; capital split; whether the ledger starts at $130 or $110; Ubuntu 26.04 install error on the server; Anthropic terms for a dedicated automation account.
6. Overheard: Phone Test verdict was empty once, re-run; UI revamp from his references; hardening (fuzz DNS parser, auth abuse); iOS dashboard; Alexa preset toggles; decrypting own-device traffic (plan only); GitHub push polish; cleanup of leftover r15/Gemini files on his laptop only on "clean up".

## 12. Lessons and tool quirks
- The sandbox and the laptop VM cannot reach the board or the LAN; every board test is a user double-click and a result file.
- `sed -i` drops exec bits on `.command` files; re-run `chmod +x`. `web/index.html` has very long lines: patch with exact-string replacement, not full reads.
- iOS profiles cannot set plain-IP DNS (corrected earlier mistake).
- `ssh` with `sudo` needs `-t`. Tailscale addresses are stable; the board's building address is not.
- Never claim a device was tested when only CI ran. Never ask twice for a "go" already given.
