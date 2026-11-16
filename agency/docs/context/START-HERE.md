# Agency — start here (2026-11-11)

**Next session, paste this to Fable:**
> Read every file in the folder `Claude outputs + AgencyPlan` (start with agency-playbook.md, then agency-goal-dial.md, agency-departments.md, agency-plan.md) and the project docs overheard-r16-plan.md and overheard-r16-addendum.md. Follow playbook section 1: you orchestrate Sonnet 5.5 high workers and write no code. Obey the economic guardrails (playbook section 7). Check usage first. Start with the build queue (goal dial wave first, then playbook section 4) and ask the open questions in one batch. Report in a few lines.

**Files**
- `agency-playbook.md` — practices, returns design, dashboard tabs, build queue, economics + guardrails
- `agency-goal-dial.md` — running cost ($40/month), profit definition, goal dial + Live layout change
- `agency-departments.md` — what each department does, markdown INDEX rule, UI research task
- `agency-plan.md` — architecture (folders, sandboxing, scheduler, local inference, routing, budget)
- `usage-estimate.md`, `local-models.md` — research (modelled numbers; check sources)
- `metrics.md`, `handoff-schema.md`, `compaction.md` — specs from the code
- `agency-v02.tgz` — the code (stdlib Python, simulated tree, 119 tests); unpack and run `make ci`
- `agency-v02-1440.png` — latest dashboard screenshot

**Status**: agency v0.2 built and tested (simulated). Not built: goal dial (next), schedule/locality (v0.3), returns + Business tab (v0.4), UI revamp, 3DS executive view, first real agent. Overheard R16 is separate (folder `unoq-netmon.r16`).

**Decisions**: profit target $520 (floor $500), stretch not guarantee; operations (game assets) leads, finance small and capped; trading paper first; profit reinvested; agents never hold money.
**Open questions**: playbook section 5, plus how the first month's $40 is treated against the $130.
