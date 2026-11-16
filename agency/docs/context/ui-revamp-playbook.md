# UI revamp — process, practices, product (from the Overheard R17 dashboard, 2026-11-12)
Reusable for the agency dashboard. The Overheard code itself stays outside this repo; this is the method and the design decisions.

## Process (in order)
1. **References first.** The owner sends screenshots and a few style words. Take the spirit, never copy a specific product's or game's layout, characters or art.
2. **Inventory before design.** A worker lists every panel, figure, control and API call of the current dashboard ("nothing may be lost" checklist). The rebuild is later checked against it line by line.
3. **Static mock for approval.** One self-contained page with sample data, a dark/light switch and a preview of the admin state, plus screenshots at 1440 and 390. No real code is touched until the owner approves.
4. **Owner feedback goes to the same worker** (it keeps its context), in one message, with what to keep and what to change.
5. **Rebuild in a copy** of the code (new version folder), appearance and layout only, wired to the same endpoints. CI must stay green.
6. **Fresh-context audit** (never the author), then fixes, then screenshots viewed by the orchestrator before it is called done.

## Practices
- Orchestrator plans, briefs and audits; Sonnet high-effort workers do the work. Brief = MAIN IDEA / files owned / off-limits / CRITERIA / report word cap.
- UI skill: `ui-ux-pro-max`. Reviewers: ECC (`ecc:security-reviewer`, `ecc:python-reviewer`).
- Smallest complete change (ponytail). No libraries for things a few hundred lines can do; the page stays one self-contained file that works offline.
- Motion costs battery: animate only on real events, zero frames when idle or when the tab is hidden, reduced motion on phones and when the system asks for it. One interface for all screen sizes.
- Privacy by state: the locked (default) view shows no sensitive detail (for Overheard: no domain names in the page, tooltips, hidden text or requests); extras live behind the unlock. Test it.
- Accessibility is not optional: text contrast ≥ 4.5:1 in dark and light, visible focus, touch targets ≥ 44 px, state never by colour alone, a text alternative for the map.
- Untrusted text (device names, model output) is inserted as text, never as HTML.
- Report what was not verified; anything needing real hardware is listed, not assumed.

## Product decisions (owner)
- Game-like, not a flat "AI dashboard": raised, bevelled controls that sink when pressed; framed panels with bracketed corners; a HUD header of counters; pixel/monospace display type used sparingly. Silent.
- Main feature: a three-dimensional mind map (own perspective projection, drag/touch/arrow keys to rotate, nearer nodes larger and brighter, a minimum size so far nodes stay readable). For the agency: agents and departments are the nodes; handoffs are the pulses.
- Two small readout bars (performance, network) in the style of a game's performance overlay, using figures already available.
- Colour: the default theme has no blue and no purple. Base = black, greys, white, silver; soft pastels (mint, peach, butter, blush, sage) used sparingly for state. Blue/purple only as optional themes.
- Skins by formula: each theme is one small palette (tint hue and strength, accent hue and strength); dark mode, light mode and all depth shading (highlight edge, shadow edge, bevel, pressed offset, glow) are computed from it. 48 palettes give 96 consistent skins.
- The tokens and component styles sit in one delimited block so they can be copied into the agency dashboard.
- Handheld (New 3DS XL) version comes after the main dashboard: simplified map and status on the top screen with the small bars along the bottom, command buttons and a 9-digit unlock pad on the touch screen, one dark and one light mode.

## Status
Overheard R17 was rebuilt on 2026-11-12 (appearance only, same endpoints, tests green, fresh security audit with four low findings fixed) and is awaiting the owner's test on the real board. When it is accepted, copy its token/component block into this repo and restyle the agency dashboard with the same steps.

## 3DS app references (owner-supplied, known-good homebrew apps; for structure and ideas only, check each licence before reusing code)
- https://github.com/skrimby1/controlmole-3ds
- https://github.com/kylie-grace/homepad-3ds
- https://github.com/Just-a-Spider/SysMon
