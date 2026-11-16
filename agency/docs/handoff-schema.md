# Handoff schema (v1)

Every agent, in every department, passes information to another agent through one kind of file: a handoff.
Same front matter, same four body sections, whoever writes it. Code: `src/agency/handoff.py`. Departments differ in
their instructions, never in this format.

## File name = routing tag
    HANDOFF__<to-dept>.<to-role|any>__<kind>__<job-id>__<seq>.md
    HANDOFF__research.analyst__assignment__job-004__002.md      broadcast: HANDOFF__all.any__decision__job-009__001.md
Tokens are lowercase letters, digits and `-` (never `_` or `.`). `seq` is 3+ digits, counted per job. The name says what the file
is for (kind), where it is going (department, role or `any`) and which job, so an agent skips files that are not its own
without opening them. `list_for(agent)` works on names alone.

## File
    # HANDOFF
    TAG: research.analyst__assignment__job-004__002        (the name without HANDOFF__ and .md)
    ---
    <front matter, exactly these keys, in this order>
    ---
    ## Context  /  ## Content  /  ## Needed from you  /  ## Attachments        (exactly these four, in this order, none empty; write `none`)

| key | value |
|---|---|
| schema_version | `1` |
| id | `<job>-<seq>`, e.g. `job-004-002` |
| title | 1-120 characters |
| from | `<dept>.<role>.<agent-id>`, e.g. `research.lead.research-lead` (Head and General are dept `command`) |
| to | `<dept>.<role>`, `<dept>.any` or `all` |
| kind | `assignment` `report` `question` `answer` `data` `decision` `escalation` `returns` |
| job | job id, e.g. `job-004` |
| created, expires | `2026-01-31T12:00:00Z`; expires may be `none` |
| priority | `low` `normal` `high` `urgent` |
| supersedes | `none` or the id of an earlier active handoff of the same job |
| token_estimate | integer: size of this handoff as the reader will load it (attachments included) |
| summary | `summary: |` then 1-3 indented lines (max 160 chars each) |

Attachments: lines `- <relative path>` or `- none` (no absolute paths, no `..`). Unknown or missing keys, other kinds, a
different order or a TAG that disagrees with the name are rejected (`validate`).

## Kind `returns` (v0.4)
A department Lead's value report to command: job `returns-<dept>-<period>` (period `YYYY-MM-DD-YYYY-MM-DD`), Content = one JSON object with keys dept, period, value_kind, headline, delta_pct, confidence, evidence, cost, efficiency, notes, extras (checked by `returns.validate`; see README). One active per Lead per period; supersede to update.

## Routing rules (enforced in `write_handoff`)
- Inside a department anyone may write to anyone. A worker may only address its own department.
- Between departments only Leads write, only to the other Lead (`<dept>.lead`, never `any`), only as `data`, `question` or `answer`:
  worker -> own Lead -> other Lead -> worker. A worker who needs another department asks its own Lead.
- Command (Head, General) addresses a department through its Lead, and may broadcast with `to: all`. A Lead reports up to command.
- Instruction files are isolated the same way: an agent reads only command roles above it, its own department and `_shared/tasks`.

## Life cycle and functions
| call | does |
|---|---|
| `write_handoff(frm, to, kind, job, title, summary, context, content, needed, attachments, priority, ttl_s, supersedes, token_estimate)` | validates, writes atomically into `departments/<to-dept>/inbox/` (`all` -> `handoffs/`), returns the file name |
| `list_for(agent, kinds=None, job=None)` | names addressed to the agent; never opens a body; archives expired files first |
| `read(agent, name)` | opens one file; only for an addressee or the sender |
| `mark_done(agent, name)` | addressee closes it: moved to `handoffs/archive/done/` |
| supersede, expire | `supersedes` archives the old file to `archive/superseded/` (only your own, or one addressed to you); `ttl_s` expiry goes to `archive/expired/` |

Every write, read, close, supersede, expire and refusal is one JSON line in the audit log. Layout: `departments/<dept>/inbox/` (delivery),
`handoffs/` (broadcasts and `archive/`). The simulator uses the same code on a bounded temp dir (300 archived files kept).
