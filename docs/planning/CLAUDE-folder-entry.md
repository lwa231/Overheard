# ArduinoQ — Claude Code entry point (2026-11-11)
Folder: `~/Desktop/ArduinoQ`. Two projects: **Overheard** (DNS ad blocker, Arduino UNO Q) and the **AI agency** (local Ubuntu server). Stay inside this folder. Ask before sudo. Never touch `unoq-netmon.old` (user's original code).

## Read first
1. `Claude outputs + AgencyPlan/START-HERE.md`, then `agency-playbook.md`, `agency-goal-dial.md`, `agency-departments.md`, `agency-plan.md`.
2. `Claude outputs + AgencyPlan/overheard-context.md` (Overheard R16 state, decisions, open items).
3. `HANDOFF.md` (R16 build handoff), `unoq-netmon.r16/` (last version run on the board) and `unoq-netmon.r17/` (new game-style dashboard, built 2026-11-12, awaiting the user's test on the board; see overheard-context.md "R17 UI revamp"). This Mac is for Overheard work only; agency work happens on the user's Windows machine from the AWL_Agency repo. Old docs `HANDOFFfromAntiGravity.md`, `3ds_admin_dashboard_plan.md` are Gemini's.
Ignore `HANDOFFforotherchatdontworryaboutthisIGNORE.md`. `trading-bot-ideas.md` and `reel-queue.md` are the user's notes.

## How the user wants you to work
- Terse, calm replies. Exact copy-paste commands. Minimal laptop interaction; results go to files you read (`last-check.txt`, `last-phone-test.txt`).
- Operating model: the main model orchestrates (plans, briefs, audits, talks to the user, writes no project code); Sonnet 5.5 high-effort subagents do all hands-on work; a fresh-context worker audits; one worker commits and packages, parallel workers never commit.
- Brief format: MAIN IDEA / files owned / off-limits / CRITERIA / report word cap. View screenshots before calling UI done.
- Once told "ready/go", keep going; do not ask again. Do not launch into a known usage limit; schedule a restart after the reset. Be economical with usage.
- Never suggest demo mode. Keep only the newest build on the laptop; delete old builds only on the user's "clean up".
- UI taste: distinctive, non-generic, dark default, Hostinger-style cards, Google-style gauge, one accent.
- Content filters (adult guard) are hard-coded and not user-disableable. Slowdown is a separate toggle.
- Honesty: label anything not tested on hardware; targets are not forecasts.

## Placement (hard, details in `Claude outputs + AgencyPlan/agency-network.md`)
Overheard stays on the Arduino. All agency code and files live only on the local Ubuntu server. The Hostinger VPS only runs the Telegram relay. The Mac only SSHes into the server. A small API links Overheard and the agency. Tailscale on every device; the Arduino is the DNS/security manager.

## Agency hard guardrails
Agents never hold payment methods or funds. Every spend, purchase, upgrade, public/outbound action and any tax/legal/platform-terms matter needs the user's per-action approval. Agents cannot change their own limits, schedules, incentives or instruction files. No evading usage limits. Trading is paper first; live only within a one-time capped budget with broker-side limits. Details: playbook section 7.

## Facts
- User: Mac `luqman_ahmed`. Board: `arduino@100.69.41.76`, hostname UnoQ1, access key in `~/netmon/data/token` on the board. Tailscale not confirmed.
- Agency money (updated 2026-11-11): $150 − $20 Claude Pro − $30 Grok = $100 ledger start; fixed cost $70/month (two Claude Pro subs, one personal and light, one dedicated to the agency, plus Grok); split of the $100: operations $40, implementation $20, research $15, marketing $15, finance $10; target $520 profit (floor $500), stretch, reinvest all profit for ~7 months; profit = revenue − $70/month − variable costs. No GPU or local models for now. Repo: `Agency_Building/` → github.com/lwa231/AWL_Agency (pushed: goal dial, v0.3 schedule, gates, v0.4 returns + Business tab; 222 tests; all simulated). Next: server install and deploy, then first real boss agent. Latest decisions: playbook section 5 "v0.3 decisions".
- Server: Ryzen 5 7600X, 16 GB DDR5-4800, iGPU only, Ubuntu 26.04 LTS install troubled.
- Agency code: `Claude outputs + AgencyPlan/agency-v02.tgz` (stdlib Python, 119 tests, `make ci`).

## Next actions
1. Goal dial wave (spec: `agency-goal-dial.md`), then v0.3 schedule + locality, v0.4 returns + Business tab (playbook section 4).
2. Overheard: `last-phone-test.txt` holds only a timestamp (no verdict). Diagnose why; re-run Phone Test with the phone on DNS `100.69.41.76`. Install and Check passed on the board.
3. Open questions for the user (one batch): trading gate, capital split, ledger start $130 vs $110 (is the second subscription already paid out of pocket?), `tailscale status`, Ubuntu 26.04 error.
4. Cleanup (only on "clean up"): `unoq-netmon.r15`, `overheard-r15.tgz`, Gemini patch scripts, `__pycache__`.
