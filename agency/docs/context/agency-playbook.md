# Agency — playbook, returns plan, economics, next-session kickoff (v3, 2026-11-11 13:05 ET)
Read with `START-HERE.md`, `agency-goal-dial.md` (running cost $40/month, profit definition, goal dial + Live layout), `agency-departments.md`, `agency-plan.md` (architecture), and project docs `overheard-r16-plan.md` / `overheard-r16-addendum.md`. Code: `agency-v02.tgz` (v0.2, 119 tests). Specs: `usage-estimate.md`, `local-models.md`, `metrics.md`, `handoff-schema.md`, `compaction.md`.

## 1. Working practices (how this chat runs — keep doing it)
**Roles**
- Fable (medium effort) = orchestrator only: thinks, plans, briefs, audits, decides, talks to the user. Writes no project code.
- Sonnet 5.5, effort high = all hands-on work (code, research, docs, tests, packaging).
- Independent auditor/finisher worker = fresh context, never the author. One worker commits and packages; parallel workers never commit.

**Brief format (every worker)**: MAIN IDEA · files owned · off-limits · CRITERIA (definition of done, incl. tests/`make ci`) · decisions already made by the user · REPORT format with a word cap (60–150). Reports state what was NOT verified.

**Waves**: 3–5 workers in parallel on disjoint files → integration worker fixes seams, `make ci` green, commit, package → checkpoint (tgz to the user; to the laptop when the Mac is linked) → update the plan doc. View screenshots of any UI before calling it done.

**Usage discipline**
- Check remaining session usage before a wave; never launch into a known limit. The 2 a.m. launch hit a limit and wasted the run; if a reset time is known, schedule the restart just after it.
- Terse replies, no progress narration, no repeating what the user can see. Planning only when usage is low.
- Ask questions in one batch (AskUserQuestion, max 4), recommended option first; proceed on the default if unanswered.

**Honesty rules**
- Label unverified claims; cite sources; say plainly when something is untested on hardware. When wrong, say so and fix (iOS profiles cannot set plain-IP DNS — corrected after research).
- Never claim a device was tested when only CI ran. Never present a revenue target as a forecast.

**Safety rules (hard)**: content filters hard-coded and not toggleable; slowdown is a separate toggle; no rogue DHCP/ARP spoofing of a shared network; trading is paper first, live only under a small capped budget the user approved once with limits enforced at the broker (never by the agent's own say-so); emails, payments, purchases and any other live action outside that approved budget need the user's per-action approval; never touch `unoq-netmon.old`; delete only with the user's OK and permission prompt; no sudo without asking. Economic guardrails are in section 7.

**User preferences**: terse calm replies; minimal laptop interaction (double-click `.command` files, results written to files Claude reads); exact copy-paste commands; never suggest demo mode; dark, distinctive, non-generic UI (Hostinger-style cards, Google-style gauge, one accent); only the newest build on the laptop.

**Tool quirks**: laptop VM cannot reach the board or the LAN; delivery to the Mac needs the chat linked to the desktop app; `device_commit_files` needs `stagedPath` under `/mnt/user-data/outputs/` + `force`; deletion needs `device_request_delete_permission` each session; ruff at `/root/.local/bin`; Overheard is stdlib-only Python.

## 2. Returns: one quantifier per department
**Mechanism**: handoff kind `returns` (same envelope as every handoff). Each lead emits one per period. Fixed fields: `dept, period, value_kind (money|output|knowledge|quality), headline {value, unit}, delta_pct, confidence (0–1), evidence [handoff ids], cost {usd, tokens}, efficiency (= return ÷ cost), notes`. Departments differ only in `headline` and an `extras` map.

| Dept | value_kind | Headline | Extras |
|---|---|---|---|
| Finance/Trading | money (PAPER until the gate; then capped live, labelled) | P&L $ | return %, max drawdown, win rate, risk-adjusted ratio, open positions |
| Marketing | money | attributed revenue $ | spend $, ROI %, cost per customer, conversions, reach |
| Operations | money | revenue / $ saved | margin %, orders, uptime %, incidents, infra cost |
| Implementation | output + quality | merged changes shipped | CI pass rate, first-pass pass rate, defects escaped, cycle time, tokens per merged change |
| Research | knowledge | usefulness index 0–100 (arbitrary, formula documented) | share of its handoffs used by others, claims verified %, sources per claim, coverage |

**Rules**: never blend paper and real money; every $ figure cites evidence handoffs and is verified by the auditor before reaching the dashboard; non-money indices are never summed with dollars. Agency net = Σ real-money returns − Claude spend − compute/power cost.

## 3. Dashboard: tabs
- **Live** (current main view): tree, processes, feed, per-agent panel. One click back from anywhere (persistent pill nav, `#live` / `#business`).
- **Business**: card per sector with headline, sparkline, delta; agency-net + ROI card; **runway card** (net revenue to date vs the next gate/purchase in section 7); small-multiple charts (dollars and indices on separate axes); sortable job table (id, department, owner, status, tokens, cost, return attributed, duration, audit result); sector detail on click.
- **Office** (queued research): 2D isometric view of agents moving and meeting, driven by the same handoff feed.
- 3DS executive view: net return, runway, sector list, department on/off toggles.
- Simulated first; real-source stubs behind the same interface.

## 4. Build queue (Fable + Sonnet waves, in order)
0. Operations first product is decided (digital game assets first; research scouts microcontroller parts). Still open: trading paper gate, capital split.
0.5. **Goal dial wave (first build)**: user-set dollar goal per period, dial above the Live feed, process graphs squeezed to the chain-of-command width, ledger-backed profit = revenue − $40/month − variable costs (spec: `agency-goal-dial.md`).
1. v0.3 — schedule + locality, sized for ONE Pro account (1–3 concurrent agents): asleep/warm/working states, per-department windows with manual toggles, a loop inside each window, clock window + usage-share cap, LRU eviction.
2. v0.4 — `returns` kind + simulator + Business tab + processes table + runway card + reinvestment ledger.
3. Markdown INDEX linter + generator (departments doc), applied to all instruction files.
4. UI revamp (user is sending references) → shared design tokens across dashboard, 3DS, later iOS. Office tab research prototype.
5. 3DS executive dashboard + possible iPhone app.
6. First real agent (boss) wired into the tree; handoff store exposed through the server.
7. Overheard R16: user runs Install / Check / Phone Test; `tailscale status` output; "clean up" of r15 leftovers.

## 5. Open questions
1. Trading paper-to-live gate: minimum weeks, or minimum return?
2. Capital split of the $130 (proposed in section 7, unconfirmed) and how the first month's $40 of subscriptions is treated against it (ledger start $130 or $110?).
3. (Answered) $520 profit, floor $500. Confirm the proposed capital split in section 7.
4. Schedule: finish-or-stop at window close; clock vs usage-share windows (my default: both).
5. What counts as a "business" (one per department, or several each)?
6. Anthropic terms on a dedicated automation account and two subscriptions — verify before relying on it.
7. Ubuntu 26.04 install: paste the exact error and I will help.
8. Rank names; tree vs radial; first real agent vs UI revamp first.
9. WIP, not in v0.3 (user, 2026-11-11): Grok subscription (~$30/month) as lead agent of the finance department. Would make liquid capital $150 − $20 − $30 = $100 and fixed cost $70/month (break-even $70). Unverified: whether a Grok chat subscription can be driven by an agent, or whether it needs the paid xAI API instead.

### v0.3 decisions (user, 2026-11-11 evening)
- Simulated only; real agents after the server is up.
- Window close: the job in hand always finishes; no new job starts after close. Windows are sized so planned work fits; only tasks the user adds may run over.
- Backlog: priority queue per department; user-added tasks rank first.
- Window type: clock window, plus a lead agent (boss/general) that hands out usage share across departments.
- Locality (cache analogy): an agent's instructions, task context and schedule stay loaded (warm) while reused, least recently used is put to sleep; everything runs on the one server.
- Executive actions (approvals included) from Telegram, 3DS, Mac SSH, desktop PC, each individually authorised by the user. Strong dashboard login UI: later.
- Deadline: planning + implementation phase done by Friday 2026-11-13 (not dashboard polish). Initial investment that day = second Claude Pro (+ Grok, WIP). Until then simulated, with weak CPU-only local models for testing.
- Usage cap: the Claude plan limit is a hard stop. No credits and no overrun until there is revenue; a job that hits the limit checkpoints and resumes in the next usage window. Later: profit funds usage credits, overrun capped at 25%.
- Name of the system: **Agency of Business**.
- Approval queue: anything that costs money or runs over (time or usage) goes to the user through the boss; the user approves or denies per item. Routine loop work runs without asking.
- Boss assistants: subordinates of the boss that read everything (read-only) and summarise the state for the user; the boss relays the user's answers down. Open: what happens to a time-sensitive approval when the user is unreachable.
- Unanswered overrun request: continues only if a user-allocated overtime fund has a surplus; otherwise the job pauses until the user answers. Fund is $0 until there is profit.
- Usage split per window (to tune by testing): operations 40, implementation 20, research 15, marketing 15, finance 10.
- Gates (decided; enforced by code, always wait for the user): spend/purchase; outbound or public action; irreversible action (delete, live trading); changes to instruction files, limits, schedules, incentives; overrun of time or usage. The overtime-fund check is code, not agent judgment, with a per-job cap set by the user.
- Stop rules per job (decided): finish check that passes/fails without a model; 3 attempts; then report blocked up the chain (lead → boss → user queue); token ceiling checked before start.
- Version control (decided): plain git on the server, one branch per job; post-commit hook sends hash + time to the Arduino's append-only log over the Overheard↔agency API; mirror to the private GitHub repo about twice a day at a settled stopping point, not per commit.
- Skills: skipped; department instruction files cover it.
- Capacity (user, 2026-11-11): no GPU and no local models for now. Workers = the dedicated Claude Pro subscription (+ Grok subscription, access unverified); the personal Pro stays light. Antigravity is excluded from the plan. A good GPU is bought from revenue later, not a cheap one now.
- Money (user, 2026-11-11, supersedes section 7 figures): Grok confirmed. Ledger starts at **$100** ($150 − $20 Claude Pro − $30 Grok). Fixed cost **$70/month**, break-even $70. Capital split of the $100 by the usage percentages: operations $40, implementation $20, research $15, marketing $15, finance $10. Work stays mostly in Claude Code instances; Grok mainly for the trading lead.
- Emergency reserve (user proposal 2026-11-11, default unless changed): of the $100, $80 is working capital and $20 is an emergency reserve. The reserve is not the overtime fund (still $0 until profit) and is spent only on the user's approval.
- Build status (2026-11-11): pushed to github.com/lwa231/AWL_Agency — v0.2 baseline, goal dial, v0.3 schedule + locality, scheduler drives the tree, ledger $100 / $70 month. Remaining waves in order: (1) gates: approval gates, approval queue with deadlines, 3-attempt stop rule, overtime-fund rule, $80 + $20 reserve, add-task from the dashboard, toggles persisted; (2) v0.4 returns + Business tab + reinvestment ledger with the capital split; (3) server: Ubuntu install, deploy, git with post-commit hook to the Arduino log, twice-daily GitHub mirror, Tailscale; (4) first real boss agent + read-only assistants; (5) Telegram approvals, strong login UI, 3DS view, UI revamp; (6) trading (paper) after the user loads methods, Grok lead.
- Test phase (user, 2026-11-11 night): small local model on the server CPU via Ollama (candidates named by the user: Llama 3.2 3B, SmolLM3 3B, LiquidAI d1-3B, nvidia LocateAnything-3B; start with Llama 3.2 3B). First real agents: boss, finance lead, operations lead; all others stay simulated. Paper trading on ETFs and crypto; the user's methods arrive next session, placeholder rule until then (labelled). Operations: simulated customers buy; the agents' outputs go to the user for review, and the review is fed back into the run. Agent network use stays behind Overheard DNS, read-only price data only. Admin rights (sudo) on the server stay with the user.
- Efficiency and locality for local-model agents (user, 2026-11-11): one shared model process; one working slot on CPU; scheduler prefers the agent whose context is already loaded (run its jobs back to back); prompt = unchanging role file first, then the variable task and latest owner feedback only (no full history); model kept loaded between jobs; caps on context and output length. Per-department OS user/service with CPU and memory caps comes when agents can run commands.
- Install + look (user, 2026-11-11 night): one-step installer (`Install Agency.command` on the Mac → `scripts/install.sh` + boot service on the server, Tailscale address only). Dashboard to be restyled to match Overheard's dashboard (its colours, cards, gauge, type from `unoq-netmon.r16/web/index.html`), still served separately on the server on its own port; merging the two dashboards is later.
- Consequences: jobs must be resumable from a checkpoint; the scheduler does not start a job that will not fit the remaining usage.

## 6. Kickoff prompt for the next Fable session
See `START-HERE.md`.

## 7. Economics and self-funding
**Server (always-on, scheduled loops)**: Ryzen 5 7600X (6 cores, AM5), 16 GB DDR5-4800 (user plans an overclock toward ~5800 MT/s; AM5 DDR5 is commonly stable near ~6000 with the EXPO profile — memory-test before trusting it, keep the stock profile as fallback), integrated graphics only (no discrete GPU yet), lots of mixed-speed storage. Ubuntu 26.04 LTS install in progress.
- **No GPU ⇒ local models are CPU-only**: roughly 1–4B-parameter quantised models at a few tokens/s — fine for tagging and classification, not real worker capacity. Real local workers arrive with the GPU (research: RTX 3060 12 GB, and 32 GB RAM). Until then workers are Claude.
- **Claude access**: two Pro subscriptions. Personal one stays light and untouched. The second is dedicated 100% to the agency. A Pro window filled in about an hour of 4–6 parallel Sonnet subagents in this user's experience, so until an upgrade expect **1–3 concurrent agents**, not 5–8, with schedules sized to the usage share.
- **Capital**: $150 start − $20 (dedicated Pro) = **$130 liquid**.
- **Target (user decision 2026-11-11)**: **$520 profit** (= $650 total from the $130; floor $500 profit). Stretch goal, not a guarantee. Lead driver = operations (game assets: ~87 sales at ~$6 net ≈ $520, arithmetic only); finance is a small risk-capped contributor, since $520 from a ~$40 slice is 13×. Proposed split of the $130 (user to confirm): operations ~$60, finance ~$40 (paper until its gate), marketing ~$15, reserve ~$15. Finance hard limits: cap on total live loss, daily stop, kill switch enforced at the broker. Purpose: fund the $200/month Max plan; then RAM and a GPU. Treat this as a **stretch target, not a forecast**: $520 in the first weeks from $130 is very aggressive, and a $200/month plan needs ~$200 of net revenue **every month**, not once. Gates for the runway card (proposed, user may change): G0 setup running → G1 first verified $1 → G2 $130 recouped → G3 $520 cumulative → G4 ≥ $200/month net for two consecutive months → upgrade to Max → RAM to 32 GB → GPU.
- **Reinvest-only period**: for the first 7 months all net revenue goes to a **reinvestment ledger** (append-only: date, source, amount, spend, balance, evidence). Purchases follow the order above; the boss proposes, the user approves each purchase.
- **Boss incentive**: net return after Claude/compute cost is the shared scoreboard; earned revenue is what funds more capacity for everyone. It is a reported metric, not a licence to acquire resources.
- **Guardrails (hard)**: agents never hold payment methods, funds or purchasing accounts; every spend, purchase, upgrade, public/outbound action and anything touching tax, legal or platform terms needs the user's per-action approval; agents cannot change their own limits, schedules, incentives or instruction files (boss edits on the user's word); no working around usage limits (no extra accounts or evasion); trading: paper first, live only within the one-time capped budget with broker-side limits; revenue claims must be evidenced and audited; log every revenue and spend event.
- **Realism**: markets are not a plausible source for 4× on $130; first revenue is more likely from digital products (game assets) and services.
