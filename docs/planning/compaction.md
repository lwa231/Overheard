# Compaction limits (v0.2)

`config/tiers.json` is the one place: `compaction_limit_tokens` by rank key (head 500,000 / general 400,000 / squad_lead 300,000 /
agent 200,000), `overrides` by agent id, and `context_window_tokens` by runtime. Limits may not rise down the ranks. Rank labels
are renamed in `config/agency.json`; the limits follow the rank key (rename a key in both files). Renaming a role needs nothing.

An agent compacts when its context reaches its limit. Effective limit = min(configured limit, the runtime's real model window);
`/api/agent/<id>` shows `tier` (configured, source, window, effective, capped) and `metrics.model` (`ctx_tokens`, `ctx_limit`, `ctx_pct`
= tokens / effective limit, `compactions`). The simulator drops context to 20% of the limit and posts a `compact` event.

## A limit cannot exceed the model's window
Anthropic's docs (platform.claude.com/docs/en/build-with-claude/context-windows, read 2026-11-11) list a 1M-token window, with no beta
header, for Claude Fable 5.2, Mythos 5.2, Opus 5.5 / 5 / 4.8 / 4.7 / 4.6, Sonnet 5.5 / 5 / 4.6 and Haiku 5.5 (and earlier Fable/Mythos 5.x);
"other Claude models, including Claude Sonnet 4.5 (deprecated)" have 200k. So 200k-500k fits every current model but 500k/400k/300k do not
fit a 200k model. Haiku 5.5 prompts over 100,000 tokens cost more. The `local` window (131,072) is an assumption: set it to the real `n_ctx`
of the inference server. Docs change; re-check before relying on these numbers. Long contexts also degrade (the docs call it "context rot"),
so a limit below the window is a feature.
