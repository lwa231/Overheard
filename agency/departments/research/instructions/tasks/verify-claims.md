---
title: Verify claims (Verifier)
---
1. Take the claim list from the Analyst's `data` handoff. One line per claim, with its cited source.
2. Trace each claim to the primary source. If only a secondary source exists, say so.
3. Re-derive every number and date from the source. Check units, time periods and whether the source has been corrected or superseded.
4. Look for independent support: a second source that does not copy the first.
5. Give each claim a verdict: confirmed, contradicted or unverifiable, plus the evidence in one line.
6. Emit a `report` to `research.lead`: verdict table first, then anything the Analyst must redo (as `question` to `research.analyst`). Never soften a contradicted verdict.
