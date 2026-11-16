# Agency usage estimate (public metrics only) - 2026-11-11

Every number has a source tag or is ASSUMPTION. Headline case = 5-8 agents ACTIVE at once (tree of 22-32 defined, most idle); 22/32 all-active are upper bounds.

Sources: [P] platform.claude.com/docs/en/about-claude/pricing | [M] platform.claude.com/docs/en/models/overview | [C] code.claude.com/docs/en/costs | [PC] code.claude.com/docs/en/prompt-caching.md | [SA] code.claude.com/docs/en/sub-agents.md | [Max] support.claude.com/en/articles/11049741 | [CCP] support.claude.com/en/articles/11145838 | [Ult] support.claude.com/en/articles/17728952 | [UC] support.claude.com/en/articles/12429409 | [PR] claude.com/pricing | [N] anthropic.com/news/higher-limits-spacex | [HW] hardware-corner.net/gpu-llm-benchmarks/rtx-4090/ | [HW2] hardware-corner.net/rtx-4090-llm-benchmarks/ | [LC] github.com/ggml-org/llama.cpp/discussions/15013

## 1. Facts found
**API $/MTok** [P] (in / out / 5m-write / 1h-write / cache-read):
| Model | in | out | 5m wr | 1h wr | read |
|---|---|---|---|---|---|
| Fable 5.2 (Mythos 5.2 same) | 8 | 40 | 10 | 16 | 0.20 |
| Opus 5.5 | 4 | 20 | 5 | 8 | 0.20 |
| Sonnet 5.5 | 2 | 10 | 2.50 | 4 | 0.10 |
| Haiku 5.5 (<=100k prompt) | 0.10 | 0.50 | 0.125 | 0.20 | 0.01 |
Multipliers [P]: 5m write 1.25x, 1h write 2x, read 0.1x (0.05x Opus/Sonnet 5.5, 0.025x Fable 5.2). Batch -50%. 1M context at flat rate (Haiku 5.5: higher tier >100k). Fast mode 2x (Fable 5.2 $16/$80).
**Context windows** [M]: Fable 5.2, Opus 5.5, Sonnet 5.5, Haiku 5.5 all 1M in / 128k out. So the 200-500k compaction limits are self-imposed.
**Plans** [PR]: Pro $20/mo ($17 annual); Max $100 = 5x Pro [Max]; Ultra $200 = 10x Pro weekly, no 5h limit if verified [Ult] (Max 20x renamed Ultra); Team Standard $25/seat, Premium $100/seat (5x Standard); Claude Code in all paid plans.
**Limits** [CCP][Max]: 5-hour session limit (Pro/Max) + weekly limit, shared by chat and Claude Code; separate weekly Fable limit on Max/Ultra. Absolute sizes (tokens, prompts, hours): UNPUBLISHED. 5h limit was doubled 2026-05-06, no baseline given [N]. Opus "uses meaningfully more quota" than Sonnet, no multiplier given (support.claude.com/en/articles/14552983). Overflow = usage credits at standard API rates, Claude Code included [UC].
**Subagents/teams** [SA][C]: subagent requests count toward the same limits; default 20 concurrent subagents; agent teams ~7x tokens of a standard session (plan-mode teammates); usage ~linear in active teammates; docs say start with 3-5. Subagents/teammates get 5-min cache TTL even on subscription (main conversation gets 1h) [PC].
**Consumption** [C]: enterprise avg ~$13/dev/active day, $150-250/month, 90% of users <$30/day. TPM guidance 1-5 users: 200-300k TPM/user. No published per-agent or per-hour token figure.
**Local tok/s, one RTX 4090, llama.cpp Q4, single stream** [HW]: Qwen3 8B 141 (4k ctx) -> 82 (32k) -> 34 (128k); 14B 84 -> 55 (32k) -> 39 (64k); 32B ~40 (4k), 34 (16k); gpt-oss 20B 191 -> 141 (32k) -> 70 (128k); Qwen3-30B-A3B 207 -> 105 (32k) -> 68 (64k). Prefill 8B: 9.3k t/s (4k) -> 2.0k (64k). [LC] Llama-2 7B Q4_0 tg: 4090 186, 3090 158, 5090 290. Range: ~35-200 tok/s/stream, falling with context. Batched aggregate throughput: not verified (only a blog headline of ~2k tok/s, page unreadable); treat as ASSUMPTION 3-6x single stream.

## 2. Model
ASSUMPTIONS (all tiers): boss/general Opus 5.5, leads/workers Sonnet 5.5, 5m-cache writes. Avg carried context = f x compaction limit (200/300/400/500k; sawtooth, so f<1). New (uncached) share of input = 1-h, billed at write price. Output includes thinking (always on in Sonnet/Opus 5.5 [C]).
| Scenario | f | cache hit h | out tok/turn | turns/h worker / lead / general / boss |
|---|---|---|---|---|
| light | .3 | .90 | 300 | 20 / 10 / 8 / 6 |
| typical | .5 | .95 | 600 | 60 / 30 / 20 / 15 |
| heavy | .7 | .97 | 1000 | 120 / 60 / 40 / 30 |
**Per agent per hour, typical** (arithmetic: turns x ctx = input; read = h x input x read price; write = (1-h) x input x write price; out = turns x out/turn):
| Tier | ctx | input Mtok/h | out ktok/h | $/h light / typ / heavy |
|---|---|---|---|---|
| worker (Sonnet) | 100k | 6.0 (60 x 100k) | 36 | 0.47 / 1.68 / 4.09 |
| lead (Sonnet) | 150k | 4.5 | 18 | 0.34 / 1.17 / 2.77 |
| general (Opus) | 200k | 4.0 | 12 | 0.70 / 2.00 / 4.65 |
| boss (Opus) | 250k | 3.75 | 9 | 0.65 / 1.83 / 4.21 (Fable 5.2: 1.13 / 2.95 / 6.39) |
Worker typical: 5.7M x $0.10 + 0.3M x $2.50 + 0.036M x $10 = 0.57 + 0.75 + 0.36 = $1.68. Input: light 0.9-1.2, heavy 10.5-16.8 Mtok/h. Per 5h session multiply x5. ~95% of input tokens are cache reads, so $ ~ context size, not turns alone.
Sanity: typical worker x 8h = $13.4 = Anthropic's fleet average ($13/day [C]); heavy x 8h = $33 > its p90 ($30). So typical ~ average dev, heavy ~ top decile.

**HEADLINE: 5-8 agents active** (boss + 1 lead + 3 / 4 / 6 workers), $ at API list price:
| Active | Mtok/h typ (boss + rest) | $/h light / typ / heavy | typ 5h session | typ 8h day |
|---|---|---|---|---|
| 5 (1 lead + 3 w) | 3.8 + 22.6 | 2.4 / 8.0 / 19.2 | $40 | $64 |
| 6 (1 lead + 4 w) | 3.8 + 28.7 | 2.9 / 9.7 / 23.3 | $49 | $78 |
| 8 (1 lead + 6 w) | 3.8 + 40.7 | 3.8 / 13.1 / 31.5 | $65 | $105 |
Mix chosen by user: boss on subscription -> API-billed part = lead + workers = typ $6.2 / 7.9 / 11.2 per h (5 / 6 / 8 active), $50 / 63 / 90 per 8h day (light-heavy at 6 active: $2.2-19.1/h). 6-active case, typical, by who is local:
| Workers local | Lead local | API $/h | API $/day (8h) | Share of $ at zero marginal cost |
|---|---|---|---|---|
| 0 of 4 | no | 7.9 | 63 | 0% (boss on sub) |
| 4 of 4 | no | 1.17 | 9 | 85% of the non-boss $ (workers = 6.7 of 7.9) |
| 4 of 4 | yes | 0 | 0 | 100% of non-boss $; only boss uses quota |
Workers are ~69% of all-in $ ($6.7 of $9.7/h) at 6 active.
**Local feasibility (6 active, 4 local workers, typical):** output 36k tok/h = 10 tok/s each, ~40 tok/s total vs 130-140 tok/s single stream [HW] -> fits. Prefill needs prefix caching and ctx <=32k; at 100k+ ctx an 8B runs ~35-50 tok/s and prefill ~2k t/s [HW]. So local workers should carry ~32k, not 200k (and local quality < Sonnet: ASSUMPTION).

**Upper bounds, all agents active** (22 = 1+1+5 leads+15 w; 32 = 1+1+5+25 w; boss/general at API Opus), $/h light / typ / heavy; 5h = x5, 8h = x8:
| Agents | all Claude | 50% workers local (typ) | all workers local (typ) |
|---|---|---|---|
| 22 | 10 / 34.9 / 84 -> typ $175 per 5h, $279 per 8h | 23.1/h -> $115 / $185 | 9.7/h -> $48 / $78 |
| 32 | 14.7 / 51.7 / 125 -> typ $259 / $414 | 31.5/h -> $157 / $252 | 9.7/h -> $48 / $78 |
Tokens typ, 22 agents: ~121 Mtok/h processed (boss 3.8, general 4.0, leads 22.6, workers 90.5); 32 agents ~181 Mtok/h. Realistic duty cycle (most idle) lands near the headline table, not here.

## 3. Can a subscription carry it? (only as far as public info allows)
- Unknowable from public data: quota size in tokens, how Opus/Sonnet/Fable weight against it, how cache reads count. Only public ratios: Max = 5x Pro, Ultra = 10x Pro weekly [Max][Ult].
- Anecdotal calibration (user's own, plan tier unknown): orchestrator + 4-6 parallel Sonnet subagents at ~80-235k tokens each exhausted a 5h window in ~1h of active work. ~5-7 agent-hours per window -> ~1-1.5 Sonnet agents sustainable across 5h on that plan, i.e. ~6x oversubscribed vs 6-active. Consistent with the model: 6 active x typ = ~32 Mtok/h processed. One Max-class sub plausibly carries the boss (+ maybe a lead), not the workers. Weekly cap is a second, unquantified limit.
- Overflow: usage credits bill at API rates [UC], so API cost table above is the ceiling for any quota overrun.

## 4. Two subscriptions
- Public: limits are per account (Max page: weekly reset time "assigned to your account", 5h window per account) [Max]; Ultra page [Ult] and credits page [UC] say nothing about multiple accounts. Anthropic's rules on running 2 personal subs for one workload: NOT FOUND - check Consumer Terms / Usage Policy before relying on it.
- If allowed, split by model to use separate buckets: A = boss/general (Opus or Fable; Fable has its own weekly limit on Max/Ultra, size unpublished [Max]); B = leads + a few Sonnet workers. Neither account's headroom is publicly quantifiable; two accounts ~ 2x the unknown, not a known number. Cache is per org/model; subscription main-conversation gets 1h TTL, subagents 5 min [PC] - run workers as separate top-level sessions to keep 1h cache.
- Keep workers off subscriptions (API/local); subs for the 1-2 high-context, low-turn agents where flat-rate wins.

## 5. Levers, ranked by effect (typical, 6 active, from this model)
1. Fewer concurrent Claude agents: cost linear (5->8 active = $8.0 -> $13.1/h).
2. Local workers for bulk: removes ~69% of all-in $ (85% of non-boss $) at 4 local workers.
3. Cache hit rate: h .95 -> .80 raises a worker from $1.68 to $3.84/h (2.3x); keep 1h TTL, avoid model/tool changes mid-session [PC].
4. Smaller carried context: halving average worker ctx (compact at 100k not 200k) $1.68 -> $1.02/h (-39%).
5. Boss reads reports, not transcripts: halving boss ctx saves ~$0.6/h (~6% of $) but is the largest share of subscription quota.
Also: thinking tokens bill as output (~21% of worker $) and can't be disabled on Sonnet/Opus 5.5 [C]; Haiku 5.5 reads at $0.01 for cheap triage [P].

## 6. Not found / weak
Published per-agent token rates; absolute subscription limits; subagent weighting vs quota; multi-account policy; verified batched local throughput on one GPU; whether the user's GPU is a 4090 (numbers are 4090 as the common upper-consumer card; 3090 ~15% slower [LC]).
