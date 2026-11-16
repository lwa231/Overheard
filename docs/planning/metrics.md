# Metrics (v0.1, simulated, shaped like the real sources)

Research (3 lookups): Grafana Cloud AI/agent observability dashboards (per-agent cost/tokens/latency/errors, "needs attention" cards, tool
error rates, eval pass rates), general agent-observability guides (token usage, cost, latency, error rate, tool calls, quality/eval scores),
vLLM/TGI/llama.cpp Prometheus metrics guides (queue depth, running requests, KV-cache use, tokens/s). Kept what a single home server with
one GPU, Claude Code sessions and local models can actually measure; left out latency percentiles/TTFT and tracing (no request-level traffic yet).

Interface: `src/agency/metrics.py` `MetricsProvider` (`sample`, `agent`, `compact`, `fleet`), key tuples are the contract.
`SimulatedMetrics` fakes them from the simulator; `CgroupMetrics` is a stub that raises `NotImplementedError` naming the paths below.
Units: cpu_pct = percent of one core, ram/vram MB, disk KB/s, times s, cost USD.

## Per agent (`GET /api/agent/<id>` -> `metrics`; compact subset in `/api/org` -> `agents[].metrics`)
| Metric | Real source later |
|---|---|
| cpu_pct | cgroup v2 `<scope>/cpu.stat` `usage_usec`, delta / interval x 100 |
| ram_mb | `<scope>/memory.current` (`memory.peak`, `memory.events` oom for alerts) |
| disk_read_kbs, disk_write_kbs | `<scope>/io.stat` `rbytes`/`wbytes` delta, summed over devices |
| (threads, not shown yet) | `<scope>/pids.current` |
| gpu_pct | `nvidia-smi pmon -c 1 -s u` SM% per pid; pids from `<scope>/cgroup.procs` |
| vram_mb | `nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits` |
| tokens_per_s, queue_depth (local) | inference server `/metrics`: llama.cpp `llamacpp:predicted_tokens_seconds`, `llamacpp:requests_deferred`; vLLM `rate(vllm:generation_tokens_total)`, `vllm:num_requests_waiting` |
| tokens_in, tokens_out, cost_usd (Claude) | usage ledger: per-request `usage` (input/output/cache tokens) from the API or Claude Code transcripts, priced per model |
| zero_cost | `runtime == local` |
| ctx_pct, ctx_tokens, ctx_limit, ctx_window, compactions | last request input tokens; ctx_pct = tokens / effective compaction limit (config/tiers.json, see compaction.md); window = model window (Claude) or server `n_ctx` (local, vLLM `vllm:kv_cache_usage_perc`) |
| job, jobs_done, queue_depth (Claude), avg_job_s, state_age_s, last_report_s | orchestrator job ledger (job start/finish/report timestamps) |
| errors, retries, audit_pass_rate | orchestrator ledger: blocked/failed runs, re-dispatches, superior's accept/reject of a report |
| uptime_s | `systemctl show -p ActiveEnterTimestamp agent-<id>.scope` |
| series (60 samples) | the provider's own ring buffer per metric (or Prometheus range queries) |

Scope path: `/sys/fs/cgroup/agency.slice/agent-<id>.scope/`, one systemd scope per agent session.
Roll-up (`agents[].rollup`, leads and above): sum of cpu, ram, gpu share, vram, tokens/s, cost, queue over the subtree, computed from the compact dicts.

## Fleet (`/api/org` -> `fleet.now` and `fleet.series`)
| Indicator | Real source later |
|---|---|
| tokens_per_s | sum of agents' tokens/s |
| claude_spend_usd vs claude_cap_usd | sum of Claude cost since local midnight; cap = `claude_daily_cap_usd` in `config/agency.json` |
| gpu_pct, vram_used_mb, vram_total_mb | `nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total` |
| cpu_pct, cpu_cores | `/proc/stat` or root cgroup `cpu.stat`, over `nproc` |
| ram_used_mb, ram_total_mb | `/proc/meminfo` (MemTotal - MemAvailable) |
| queue_depth | sum of agent inboxes + inference-server queue |
| avg_job_s | mean job duration from the ledger |
| audit_pass_rate | accepted / audited reports |
| errors_1h, retries_1h | ledger events in the last hour |

Simulation limits: per-agent GPU is a share of the card (sums to the box figure); the 24 GB card, 8 cores and 32 GB RAM are constants in `SimulatedMetrics`.
