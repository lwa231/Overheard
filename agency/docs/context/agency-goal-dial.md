# Agency — running cost, profit definition, goal dial (2026-11-11 13:10 ET)
Part of the playbook (`agency-playbook.md` sections 3 and 7). User decisions; build is queued, nothing built yet.

## Running cost and profit
- Fixed cost: **$40/month** = the two Claude Pro subscriptions. The user says this is the only thing paid for the agency. Electricity and similar are deliberately ignored.
- Break-even: $40 revenue per month (about $1.33/day).
- **Profit = revenue − fixed cost − variable costs** (marketing spend, platform/listing fees, trading losses). Profit is reinvested into the system (reinvestment ledger, playbook section 7).
- Capital note: working capital was set at $130 ($150 − $20). With both subscriptions counted at $40/month, confirm how the first month's $40 is treated in the ledger (open question).

## Goal dial (dashboard)
- The user sets a **goal in dollars for a period** (month by default, or a custom period) from the dashboard. Only the user can change it; agents cannot (guardrails).
- Position: **far right column, directly above the Live feed**.
- Dial (like the speed-test gauge): shows **net profit so far / goal**, days left, projected pace ("on pace for $X"), and a tick for break-even ($40). Colour changes with progress: red under 25%, amber 25–75%, green 75–100%, accent/gold at or over goal. Also a small label: profit counts only after fixed and variable costs.
- Data comes from the ledger (simulated first).

## Live tab layout change
- Keep all process graphs and indicator tiles, but **squeeze them to the same width as the chain-of-command box** (left/centre column).
- Right column: goal dial on top, Live feed below it.
- Phone (390 wide): dial first, then tiles, tree, feed.

## Build
- Small wave, queued before v0.3: goal setting, dial component, layout change, ledger-backed profit calculation (simulated), tests, screenshots at 1440 and 390.
