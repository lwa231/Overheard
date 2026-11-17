# HANDOFF — Overheard + Agency + Network (state at 2026-11-16 19:40 ET)
For a new Claude instance. Read it top to bottom once. No secrets are in this file; where secrets live is in section 13.

## 0. Start here (paste to the new instance)
> Read this file first. Then read `HANDOFF.md` and `docs/planning/` in the repo `lwa231/Overheard`, and the project docs. Work as the orchestrator: plan and brief, Sonnet 5.5 high-effort workers do all code, an independent worker audits. Terse replies. Do not launch work into a known usage limit. First job: the single merged dashboard (section 9). Ask the open questions (section 11) in one batch.

## Contents
1. Owner and working rules
2. Systems at a glance
3. Tailscale network and device table
4. Overheard (what is built, versions)
5. Multi-site work (r18, r19)
6. LED matrix
7. VPS (Hostinger) and VPN exit node
8. Agency project and economics
9. Requirements still to build
10. Everything we told the user to run (command library)
11. Open questions
12. Caveats, mistakes and findings
13. Where things live, and secrets
14. Tested vs untested
15. Next steps in order

## 1. Owner and working rules
- GitHub `lwa231`; Mac user `luqman_ahmed` (hostname `lmans-mac-pro`); time zone America/New_York. Dictates by voice (long, loose messages). Humour and the occasional curse are fine; Claude does not curse back unless he does a lot.
- Terse, calm replies. Exact copy-paste commands. Minimal laptop interaction. Once told "go/ready", keep going and do not ask again. Ask questions in one batch. He is repeatedly near his usage limit: be economical, no fan-outs unless asked, never launch work into a known limit.
- Operating model: the main model (Fable, medium effort) is orchestrator only (plans, briefs, audits, decides, talks to the user, writes no project code). Sonnet 5.5, high effort, does all hands-on work. A fresh-context worker audits; one finisher commits and packages; parallel workers never commit. Brief format: MAIN IDEA / files owned / off-limits / CRITERIA / report word cap; reports say what was NOT verified. View screenshots before calling UI done.
- UI taste: distinctive, not generic; dark default; Hostinger-style cards (soft rounded cards, stat tiles with sparklines, pill badges, one accent) and a Google speed-test gauge.
- Hard rules: content filters (adult guard) are hard-coded and not disableable; slowdown is a separate toggle. Never touch `archive/unoq-netmon.old` (his original code). Stay inside `~/Desktop/ArduinoQ`. Ask before sudo. Never suggest demo mode. No secrets in repos or chat. Keep only the newest build on his laptop; delete old builds/staging only on his "clean up". Label anything untested on hardware. Targets are not forecasts.
- Security habit: he sometimes pastes secrets into chat. Do not store them, do not repeat them, tell him to rotate if they were real.

## 2. Systems at a glance
| System | Where | Role |
|---|---|---|
| Apartment board | Arduino UNO Q, hostname `UnoQ1`, Tailscale `100.107.57.35` | Running Overheard (DNS filter + dashboard). Verified working |
| Home board | Arduino UNO Q, hostname `IsaUnoQ`, Tailscale `100.119.170.46`, house Wi-Fi `192.168.68.63` | Overheard installed 19:17; first Check ran before it finished loading (timing). Needs a re-check |
| Local server | Ubuntu, Tailscale `100.124.220.78` (`awlserver`), Ryzen 5 7600X, 16 GB | Will run the agency. Agency code lives ONLY here |
| VPS | Hostinger Ubuntu, Docker, Tailscale `100.119.85.78` (`boston-hvps`) | Tailscale exit node (works); firewall not applied yet |
| Mac | `100.89.28.119` | Main workstation; uses the dashboard app |
| Windows PC | `100.118.14.25` (`corsair-machine`) | Can run commands at the apartment if needed (.command scripts are Mac-only) |
| iPhone | `100.83.206.44` (`babatundae`) | Dashboard + DNS by manual setting |
| Nintendo 3DS XL | no Tailscale | `/3ds` admin page; separate 3DS app being built by another session |

## 3. Tailscale
- Free plan, GitHub login. Joined: both boards, local server, VPS, Mac, Windows PC, iPhone. Tailscale sees metadata only (who is online), not traffic or DNS lookups. Turn on two-factor on the GitHub account; consider Tailnet Lock; Headscale on the VPS is the fallback if metadata bothers him.
- IMPORTANT correction: the apartment board's Tailscale address is `100.107.57.35`. `100.69.41.76` and `100.69.33.51` were its building-network addresses (they changed; Tailscale addresses do not). Use Tailscale addresses everywhere.
- Policy (user): ONLY his personal devices and the boards are in Tailscale. Other people's devices must NOT need it. They are monitored simply by using a board as their DNS (shown in the dashboard), and only while on a network where the board is reachable.
- Recommended later: Tailscale ACL tags (`tag:board`, `tag:server`, `tag:vps`, `tag:mac`) to control who reaches what; do not relay control traffic through the boards.

## 4. Overheard
Python stdlib-only DNS ad blocker + network monitor + token-gated dashboard, systemd service on the board.
- DNS: ~78k blocklist, DoT upstream with ~1.5 s fallback to plain UDP + 60 s breaker (r19 adds a second encrypted upstream, Quad9 DoT, before plain UDP; not in `--strict`), per-client rate limit, allow-list + `--allow-extra`, SafeSearch rewrite.
- Adult guard hard-coded, very explicit matches only; YouTube never flagged; slowdown is a persisted toggle (default off).
- Server-side lock: locked view "Quiet."; no domains while locked. `POST /api/unlock {secret}` → cookie `ovu` (30 min, 5 failures/min per address). Access key (`?key=`, cookie `ov`) is separate. Press P or click the title to unlock.
- Fingerprinting, SQLite profile DB (16 MB cap), 48 skins, speed test gauge, board vitals, topology with gateway, refused-sources pill, `/3ds` page (untested on console).
- Versions: r14 (original look) → r15 (Gemini/AntiGravity, broke things) → r16 (rebuilt, audited) → r17 (LED animation skins, design work) → r18 (configurable board address) → r19 (sites summary, network kit; added by another session into the r18 folder). Current work folder: `unoq-netmon.r18/` in the repo.
- Status: apartment board "very smooth"; speed test about 188 down / 122 up with only the board's DNS; phone and Mac use it.

## 5. Multi-site (r18 + r19)
- r18 (mine): `board.conf` (BOARD_USER, BOARD_HOST, BOARD_MDNS, SITE) read by every `.command`, `scripts/*.sh`, the Makefile and `tools/make_profile.py` via `scripts/board.sh`. One file per site in `sites/<name>.conf` (`apartment.conf` now holds `100.107.57.35`; `home.conf.example` template; `home.conf` created on his Mac with `100.119.170.46`). Override per run: `SITE=home BOARD_HOST=<addr>`. Tests `tests/test_r18_board.py`.
- r19 (other session, commit `35c1101`, unverified on hardware): `peers.json` lists other boards; the dashboard shows peers' LOCKED stats over Tailscale (`/api/sites`, `/api/site`); `Link Sites.command` writes peer files (asks each board's sudo password, writes `last-link-sites.txt`); `Set Board Address.command` / `net_static.sh` gives the board a fixed Wi-Fi address with a 90 s timed revert (only over the Tailscale address); `Check VPS.command` / `vps_check.sh` read-only exit-node check (reads `vps.conf`, copy from `vps.conf.example`); second encrypted upstream; docs `apartment-subnet.md`, `multi-site.md`.
- What this is NOT: a merged dashboard. It is a per-board dashboard plus a summary of the other board.

## 6. LED matrix
- 8x13 matrix; characters + skins (matrix, stars, fish, ants, meteor) baked from `led/sprites/*.txt` and `src/overheard/ledanim.py` by `tools/build_sprites.py` into `sprites.json` and `led/app/sketch/sprites.h`.
- Meteor now draws three meteors per cycle (29 frames).
- The Linux-side app `led/app/python/main.py` polls Overheard at `http://172.17.0.1:8080/api/led` (the board as seen from App Lab's container) and needs `python/token.txt`. Earlier it failed silently because that file never existed; `Install LED Sketch.command` now writes it over SSH and the app prints status lines in App Lab's console. User confirmed it works on the apartment board.
- Upload path: `Install LED Sketch.command`, import `led/app` into Arduino App Lab, press Run. Needs doing separately per board (USB). Home board LED not set up yet.
- NOT a feature: both matrices showing the same sprite. Each board follows its own dashboard. Idea: home board reads the apartment's `/api/led` over Tailscale (part of unified dashboard "apply to all").
- App Lab shows the home board twice: USB entry "Pinewood-UnoQ" and Wi-Fi entry "IsaUnoQ"; the board's own hostname is `IsaUnoQ`, so probably the same board (USB name differs). Cosmetic; scripts use Tailscale addresses.

## 7. VPS (Hostinger)
- Repo `lwa231/AWL_Overheard_VPSVPN` (private): `vps/bootstrap.sh` (Tailscale + forwarding + exit node), `vps/harden.sh` (ufw; must type capital `YES`), notes in `docs/`, branch `setup-docs`.
- Done: Tailscale installed; advertised as exit node; approved in the admin console; user tested from phone, speeds about the same.
- NOT done: firewall (he typed lowercase `yes`, it cancelled), `docker ps` check (Docker can bypass ufw), SSH over Tailscale test (`ssh root@100.119.85.78`), reboot for a pending kernel update, move off the root login.
- Placement (user decision): the VPS holds NO agency code. Roles: VPN exit node now; later messaging relay.
- Messaging decision: iMessage has no bot API. Plan: a private chat page reachable only over Tailscale; optional self-hosted notifier. Telegram was offered but he prefers the most secure/easiest. Approvals over any chat need a confirmation code.

## 8. Agency project (full detail in `agency/` and `docs/planning/`)
- Personal "AI agency" on the local Ubuntu server: one boss agent; tree Head → General → Squad Lead → Agent (renameable in one config). Five departments with their own instruction directories: research (built first), implementation, marketing, operations, finance/trading. Handoff files with one schema and a tag in the filename; kinds assignment/report/question/answer/data/decision/escalation + planned `returns`; cross-department handoffs via leads only.
- Compaction (Claude agents only): workers 200k, squad lead 300k, general 400k, boss 500k; local models run at their real context.
- Sandbox: process sandbox + git worktree per agent (not V8 isolates, not Kubernetes); per-agent unix user, cgroups, nftables classes, SQLite queue, one shared inference server. Scheduling: looping windows with manual toggles, locality like a CPU cache; 1–3 concurrent agents on one Pro account.
- Built: v0.2 (simulated tree, 119 tests, `make ci`) in `agency/`. Not built: goal dial, v0.3 schedule+locality, v0.4 returns + Business tab, UI revamp, 3DS executive view, real boss agent, Office tab.
- Goal dial (queued first): user sets a dollar goal for a period; dial above the Live feed that changes colour; process graphs squeezed to the chain-of-command width.
- Economics: $150 − $20 = $130 liquid; two Claude Pro subs ($40/month; one personal and light, one dedicated to the agency); target $520 profit (floor $500) as a stretch, not a forecast; profit = revenue − $40/month − variable costs; reinvest all profit ~7 months (order: Max plan, RAM, GPU). Operations (digital game assets first) leads; finance/trading small, paper first, then a capped live budget with broker-side limits.
- Hard guardrails: agents never hold payment methods or funds; every spend/purchase/upgrade/public action/tax-legal-terms matter needs the user's per-action approval; agents cannot change their own limits, schedules, incentives or instruction files; no evading usage limits; evidence and audit for revenue claims.
- Server: Ubuntu 26.04 LTS install had trouble (error not yet shared). No GPU; CPU-only small local models until one is added (RTX 3060 12 GB researched).

## 9. Requirements still to build (priority order)
1. **ONE unified dashboard across boards (user's top ask, 2026-11-16):** merged device list from all boards (home + apartment), no visible per-site tabs; everything done in the dashboard applies to ALL boards (slowdown, LED sprite, lock/unlock, allow-list, settings); the single-board view hidden a couple of clicks away; a device seen by two boards is one device (merge by Tailscale address, then fingerprint); each board still works alone if the other is down; offline board shown as stale. Build on r19 `peers.py` / `/api/sites`. Security: per-site keys, peers accept writes only from tailnet addresses of known boards. Also a board switch inside the dashboard (the user asked for "a single button" but it was not built).
2. Other people's devices must be monitorable WITHOUT Tailscale (they just use the board's DNS). Nothing to build for that except showing them; the unified view must include them.
3. Restrict the dashboard port 8080 to the tailnet (it is token-gated but listens on all interfaces); not yet confirmed closed to other LAN devices.
4. Same LED sprite on both boards (part of 1).
5. Gate (planned): separate program driving an nftables firewall using Overheard's DNS (allow a device only to addresses it recently resolved); exit node on a board is possible but the board is small, Wi-Fi only and a single point of failure; start with the server's outbound traffic; fail-open vs fail-closed choice needed.
6. UI revamp from his references (tokens → components → dashboard → 3DS → iOS); iPhone home-screen meta tags (icon, full screen).
7. Home router DHCP DNS → home board's LAN address (needs a fixed address / reservation); do only on a network he administers.
8. Agency goal dial, v0.3, v0.4 (section 8).

## 10. Command library (what the user was told to run)
Always check the board's Tailscale address, not the building address.
- Mac DNS to a board: `sudo networksetup -setdnsservers Wi-Fi <ip>`; flush: `sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder`; test: `dig @<ip> doubleclick.net +short` (expect `0.0.0.0`); undo: `sudo networksetup -setdnsservers Wi-Fi empty`. Use one board at a time (two make macOS switch between them).
- Ubuntu server (systemd-resolved): write `/etc/systemd/resolved.conf.d/overheard.conf` with `[Resolve]`, `DNS=<ip>`, `Domains=~.`, restart `systemd-resolved`. Windows (PowerShell admin): `Set-DnsClientServerAddress -InterfaceAlias "Wi-Fi" -ServerAddresses <ip>`; undo `-ResetServerAddresses`. iPhone: Settings > Wi-Fi > (i) > Configure DNS > Manual.
- Repo on the Mac: `cd ~/Desktop/ArduinoQ/Overheard && git pull && cd unoq-netmon.r18`.
- New board install (the sequence used for the home board): `cp sites/home.conf.example sites/home.conf`, set `BOARD_HOST=<tailscale ip>` and blank `BOARD_MDNS=`; `export SITE=home`; `bash scripts/setup.sh` (one time; password twice); `bash "Install Overheard.command"`; wait about a minute; `bash "Check Overheard.command"`. Dashboard: `OVERHEARD_DIR=$PWD bash launcher/Overheard-launcher.sh`. Link boards: `unset SITE; bash "Link Sites.command"`.
- Tailscale on a board: `curl -fsSL https://tailscale.com/install.sh | sh; sudo tailscale up` (via `ssh -t arduino@<addr>`), then `tailscale ip -4`.
- Read a board's unlock secret: `ssh arduino@<tailscale ip> 'cat ~/netmon/data/unlock'`; access key is `.../token`. Change the unlock secret: write the new value to that file and restart the service with `ssh -t` (sudo needs a terminal). Minimum 12 characters recommended; the 3DS keypad may only support digits (unchecked).
- Dashboard app (`~/Desktop/ArduinoQ/Overheard.app/Contents/MacOS/Overheard`): the user was given a replacement launcher script that lists the boards from `sites/*.conf` and asks which to open, then opens `http://<ip>:8080/?key=<token>`. Old script was hard-wired to the building address (that is why it failed). Not run by Claude.
- VPS: see section 7; firewall `sudo bash vps/harden.sh` only after an SSH test over Tailscale.
- Phone shortcut: Safari → `http://<ip>:8080/?key=<token>` → Share → Add to Home Screen; or Shortcuts "Open URLs". Icon file: `branding/icon-1024.png`.

## 11. Open questions
1. Mesh/router: which brand? Does he administer the apartment mesh or only the home router? (Determines whether DHCP DNS can be set; some mesh systems only change WAN DNS.)
2. Did the home board's second Check pass (service up, DNS answers, `0.0.0.0`)? Did `Link Sites.command` run? Send `last-check.txt`, `last-link-sites.txt`.
3. Which board hosts the dashboard (either, mirrored)? Fingerprint sharing across sites (privacy)? Conflict rule (last write wins)?
4. VPS: `docker ps` output, SSH over Tailscale test, run the firewall.
5. Agency: trading paper-to-live gate; capital split of the $130; ledger start $130 or $110 (is the second subscription already paid personally?); Anthropic terms for a dedicated automation account; the Ubuntu 26.04 install error; first real agent vs UI revamp first.
6. Tailnet Lock now, or Headscale?
7. Fail-open vs fail-closed for Gate; fallback resolver if a board is down.

## 12. Caveats, mistakes, findings
- iOS profiles cannot set plain-IP DNS (only DoH/DoT). Corrected after an earlier wrong promise. So iPhone DNS is manual.
- Building NAT: all devices behind the building Wi-Fi look like one public address to a board; apartment-board monitoring of other tenants is poor and risky; keep it for own Tailscale devices. Public ranges were added via `--allow-extra` (installer keeps them).
- `100.x` building address vs Tailscale address confusion (section 3). Use Tailscale.
- Check Overheard right after Install can say "NOT answering": the service is still loading lists (about a minute). Wait and re-run. `sysctl: net.core.default_qdisc` warning from `setup.sh` is harmless.
- `sed -i` drops exec bits on `.command` files: re-run `chmod +x`. `ssh` + `sudo` needs `-t`. Typing a file name alone in zsh tries to execute it. `YES` must be uppercase in `harden.sh`.
- `Check Overheard` prints the unlock secret into `last-check.txt`: never commit or paste it. Secrets have been in chat (they must be treated as exposed; rotate): the unlock secret appeared several times and the user pasted one other credential. Not stored anywhere by Claude.
- The first 2 a.m. overnight run failed: workers hit the 5-hour limit and nothing restarted them. Lesson: schedule a restart after a known reset; never launch into a limit.
- Gemini's r15 edits broke the dashboard (see section 4); r16 fixed them; `archive/gemini/` keeps its scripts and handoff for reference only.
- `git clone` for the GitHub repos: private repos need the Claude GitHub app to be granted that repository (Settings > Applications > Claude > Repository access), not the Mac's token. Push to `main` was done with the user's go-ahead.
- Public repo: addresses of the user's building range and the VPS public IP were replaced with documentation addresses (203.0.113.x, 198.51.100.x) in the pushed copies. Tailscale 100.x and private LAN addresses are in the docs (not routable from outside).
- One browser test fails in Claude's sandbox: `tests/test_r17_page.py::test_admin_shows_feed_and_locking_clears_it` (admin feed empty). 262 other tests pass. Not investigated.
- Two boards on one dashboard raises privacy questions (fingerprints and other people's browsing). At the apartment, guests' data should stay in the locked view; tell housemates.
- Phone-test (`last-phone-test.txt`) once returned only a timestamp (no verdict); not diagnosed.

## 13. Where things live, and secrets
- GitHub: `lwa231/Overheard` (public, `main`): root = r17; `unoq-netmon.r18/` = current (with r19 additions); `archive/` (old, r15, r16, r17-design, `gemini/`); `agency/`; `launcher/`; `docs/planning/`; `HANDOFF.md`. `lwa231/AWL_Overheard_VPSVPN` (private): VPS scripts.
- Project "Arduino" docs: `claude/overheard-unified-dashboard.md` (requirement), `agency-network.md`, `overheard-context.md`, `agency-playbook.md`, `agency-plan.md`, `agency-departments.md`, `agency-goal-dial.md`, `agency-start-here.md`, plus older Overheard handoffs.
- User's Mac `~/Desktop/ArduinoQ/`: `Overheard/` (clone), old folders `unoq-netmon.old|r15|r16|r17`, `Overheard.app`, `Claude outputs + AgencyPlan/`, `Agency_Building/`, `CLAUDE.md`, `HANDOFF.md`, result files (`last-check.txt`, `last-phone-test.txt`, `last-tailscale.txt`, `last-led-install.txt`), leftover staging (`_repo-stage`, `_repo-stage.tgz`, deletable on his "clean up"), Gemini's patch scripts and r15 leftovers (clean up only on his word). Personal notes not in the repo: `trading-bot-ideas.md`, `reel-queue.md`, an unrelated handoff.
- Secrets (never commit, never paste): board dashboard access key `~/netmon/data/token` and unlock secret `~/netmon/data/unlock` on EACH board; `led/app/python/token.txt` (generated); `vps.conf` (VPS login); GitHub/Tailscale credentials.

## 14. Tested vs untested
- Verified by the user on the real apartment board: install, DNS answering, ad blocking, DoT, phone and Mac use, LED sketch following the dashboard, the dashboard launcher (first version), Tailscale exit node on the VPS (speed about the same), Mac SSH over Tailscale to the apartment board, home board Tailscale join + install (service started).
- Tests in CI: 262 pass, 1 browser UI test fails (section 12). Agency v0.2: 119 pass.
- Never run on hardware: r19 features (sites summary, Link Sites, Set Board Address, Check VPS, Quad9 fallback), the new multi-board launcher app, `/3ds` on a real console, the Apple profile, Android, Gate, the VPS firewall, Linux and Windows DNS commands, a second Check on the home board.

## 15. Next steps in order
1. Home board: wait, re-run `SITE=home bash "Check Overheard.command"`; if DNS still fails send `journalctl -u overheard -n 30`. Then `Link Sites.command`; read `last-check.txt` and `last-link-sites.txt`.
2. Read r19 (`peers.py`, `server.py` sites routes, `index.html` changes), then build the single merged dashboard (section 9, item 1) with a hidden per-board view and a board switch; tests, screenshots at 1440 and 390; deploy to both boards via `SITE=<name>`.
3. Lock 8080 to the tailnet; per-site keys.
4. VPS: `docker ps`, SSH over Tailscale, `harden.sh`, reboot, non-root user.
5. Set the Tailscale global nameserver / router DHCP DNS as appropriate; fixed address for the home board.
6. Agency: goal dial wave, v0.3, v0.4; answer the open questions in section 11.
7. Gate, UI revamp, iPhone icon/home-screen tags, 3DS app (other session building it), clip/campaign research (other session, parked).
