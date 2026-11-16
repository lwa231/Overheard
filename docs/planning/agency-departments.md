# Agency — departments, markdown rule, UI research (2026-11-11 13:05 ET)
Read together with `agency-playbook.md`.

## Departments
- **Research** — serves everyone. Topics for others on request. For operations/finance: manufacturers and suppliers, where to sell, at what price, how to undercut competitors. May split into per-department research later.
- **Finance/Trading** — given a fixed slice of the $130 and its own indicators. Decided: paper first, then a small capped live budget with limits enforced at the broker, approved by the user once; the gate is still to be set. Detailed design in the Fable run.
- **Operations** — runs the e-commerce. Decided: digital game assets first (no inventory, no shipping); research scouts microcontroller parts (hackathon/student buyers; margins on parts are the draw) for later. $130 is small for physical inventory and fees.
- **Implementation (build)** — builds the agency itself: projects the user passes down through the boss; build leads extend finance, marketing, the dashboard and the server infrastructure. The agency evolves itself.
- **Marketing** — markets what operations sells and what research learns. Works with research and operations; stays out of build and finance.

## Markdown rule (all instruction and handoff files)
- Files may be long and detailed, but every file starts with a short **INDEX block** (<=12 lines): title, purpose in one line, then one line per section: anchor, what's in it, approx tokens. Agents read the index first and jump to the one section they need; they do not read whole files.
- Handoff names/tags (see `handoff-schema.md`) already let agents skip files without opening them; the INDEX is the second filter.
- Enforce in code: a linter checks the INDEX exists, anchors resolve and token estimates are within tolerance; a tool regenerates indexes; CI fails on drift. Split a file when a single section exceeds a size cap.

## UI research (queued worker task)
- Look at how others visualise agent teams as 3D/2D "offices" where agents move and meet; extract what is useful. The movement visualises the same file-based handoffs, not a second system.
- Route: third tab **Office**, 2D isometric canvas first (cheap, works on phones), 3D only if it earns its cost. Driven by the existing event feed.
- Deliverable: short research doc + one prototype, no restyle of existing tabs.

## Open questions
1. Trading: minimum paper weeks or minimum return before the capped live budget?
2. Capital split of the $130 (unallocated for now).
