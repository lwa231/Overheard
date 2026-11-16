# Agency of Business — Claude Code entry point (written 2026-11-12)
Private repo `lwa231/AWL_Agency`. This file lets a new machine (e.g. Windows) pick up where the Mac session stopped. No device addresses are stored here on purpose: get them from `tailscale status`.

## Read first
`docs/context/agency-playbook.md` (section 5 "v0.3 decisions" holds every decision from 2026-11-11), then `agency-goal-dial.md`, `agency-departments.md`, `agency-plan.md`, `README.md`.

## How the user wants you to work
- Terse, calm replies; exact copy-paste commands; be economical with usage (check usage before each wave, keep under the ceiling the user names).
- The main model only orchestrates (plans, briefs, audits, talks to the user, writes no project code). Sonnet high-effort subagents do the hands-on work. A fresh-context worker audits (never the author); one worker commits; parallel workers never commit.
- Brief format: MAIN IDEA / files owned / off-limits / CRITERIA / report word cap. View screenshots before calling UI done.
- Ponytail plugin on (smallest complete change). ECC reviewers for audits (`ecc:python-reviewer`, `ecc:security-reviewer`).
- Never suggest demo mode. Honesty: label anything unverified; targets are not forecasts.

## Hard guardrails
Agents never hold payment methods or funds. Every spend, purchase, upgrade, public/outbound action and any tax/legal/platform-terms matter needs the user's per-action approval. Agents cannot change their own limits, schedules, incentives or instruction files. No evading usage limits. Trading is paper first; live only within a one-time capped budget with broker-side limits. Admin rights (sudo) on the server stay with the user.

## State (2026-11-12)
- Code: stdlib-only Python, `make ci` (278 tests + ruff + smoke). Built and pushed: goal dial, v0.3 schedule + locality, approval gates + stop rules, v0.4 returns + Business tab, test mode (local-model agents, paper trading on crypto, owner review), one-step installer.
- Money: ledger starts $100 ($80 working: operations 32, implementation 16, research 12, marketing 12, finance 8; $20 emergency reserve). Fixed cost $70/month (two Claude Pro + Grok). Goal $520 profit, stretch.
- Server: Ubuntu Server 26.04, user `awl`, host `awlserver`, wired, LUKS disk with TPM auto-unlock, on the user's Tailscale network, DNS through the Overheard board. Repo on the server: bare `~/agency.git`, checkout `~/agency`. Mac → server SSH by key.
- Not done / unverified: the installer has never been run; no real model has been used (Ollama + `llama3.2:3b` to be installed by the user); ETF price source not chosen (crypto only); SSH password login still on; twice-daily GitHub mirror job; commit log on the Arduino; "rules" gate not enforced on the real instruction/toggle endpoints; simulated history starts 2026-09-01 and must be reset before real agents run.

## Next
1. Run the installer on the server, enable test mode (`real_agents` in `config/agency.json`), first real-model run, log seconds per job.
2. Restyle the dashboard to match the Overheard dashboard (colours, cards, gauge, type), still served separately on the server.
3. User's trading methods (to be supplied), ETF source, Telegram approvals, strong login UI, first Claude-backed boss agent after the subscriptions are bought.

## New machine setup
```
git clone https://github.com/lwa231/AWL_Agency.git
```
Plugins (in Claude Code):
```
/plugin marketplace add anthropics/claude-plugins-official
/plugin marketplace add rebelytics/one-skill-to-rule-them-all
/plugin marketplace add DietrichGebert/ponytail
/plugin marketplace add Jakeschincariol/day-trader-skill
/plugin marketplace add https://github.com/affaan-m/ECC.git
/plugin install claude-code-setup@claude-plugins-official
/plugin install task-observer@one-skill-to-rule-them-all
/plugin install ponytail@ponytail
/plugin install day-trader-skill@day-trader-skill
/plugin install ecc@ecc
```
The `terse` skill ships in `.claude/skills/terse`. The `ui-ux-pro-max` skill (3.7 MB) is not in the repo; copy `~/.claude/skills/ui-ux-pro-max` from the Mac if wanted. Git remote for the server: `git remote add server awl@<server tailscale address>:agency.git`.
