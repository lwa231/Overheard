# Overheard (AWL) dashboard: 14 visual directions

Provenance: items marked [V] had their source page fetched this session and the specifics (fonts, hex values, rules) come from it. Items marked [K] are from general knowledge; the URL is the canonical page but was not fetched, so hex values are my proposals, not the product's. Treat all hex values as starting points.

Shared constraint: the heat ramp (blue>cyan>green>yellow>orange>red) must survive any theme. See best practices at the end.

---

## 1. Nothing-style dot-matrix [V]
Monochrome ink on near-black (or white), no shadows, 1px hairlines, 8px radius. Headline is dot-matrix type, labels are uppercase mono. One signal colour only.
- Type: Doto or Ndot-alike (Google Fonts "Doto") for headline, Space Grotesk 300 for body, Space Mono uppercase 11px for labels. Nothing itself uses Ndot / NType82 / LatteraMono, uppercase mono 11-14px for all utility text.
- Palette: #000000, #0B0B0C card, #E5E7EB hairline, #585A5A muted, #FFFFFF text, signal #FF3B30.
- Interaction: headline "YouTube, playing video" renders as a dot grid that flips dots on change (like the LED matrix on the board itself).
- Device web: dots on a dotted grid, devices are filled circles, lines hairline white at 30%. Heatmap: squares become dots, size plus brightness encodes value, ramp only on the hottest 10%.
- Why it fits: the board has an LED matrix, so the dashboard can echo it.
- Source: https://www.shadcn.io/design/nothing

## 2. Teenage Engineering instrument panel [V]
Hard edges (radius 0), spec-grid cells separated by 1px black gaps, mono labels at 0.12em tracking, single-focus modes with no nested nav.
- Type: Space Mono / JetBrains Mono 400; scale 9/11/13/16/22/48.
- Palette: #FF6600 orange, #E65C00 hover, #D4D4D4 aluminium, #F5F5F5 panel, #000, OLED green #00FF66 for live values.
- Interaction: four always-visible "knob" parameters (time window, device filter, blocked-only, resolution) mapped to arrow-key / drag dials; 100ms background transitions; level meters bounce on each lookup.
- Device web: devices as labelled hardware jacks with patch-cable curves. Heatmap: 7x24 grid of LED-like cells with 1px black gaps.
- Source: https://blakecrosley.com/guides/design/teenage-engineering (author notes the CSS is illustrative, not TE's live site). Product ref: https://teenage.engineering

## 3. Neo-brutalism [V]
Thick 3-5px black borders, zero radius, hard zero-blur offset shadows, flat saturated fills, big all-caps headings.
- Type: Archivo Black / Space Grotesk 700 for headings, Space Mono for numbers. Guide specifies 48-72px caps headings, 16-18px body.
- Palette: #000, #FFF, accent yellow #FFE600, blue #2F5BFF, red #FF3B30, paper #F4F0E6.
- Interaction: buttons translate(2px,2px) and shadow shrinks 4px>2px on press with `transition: none`. Blocked pills are stamped red with a slight -2deg rotation.
- Device web: chunky square nodes, thick black edges. Heatmap: bordered cells with hard shadow on hover.
- Caveat: reads loud; heat ramp on yellow card needs checking.
- Sources: https://joshua31324324.github.io/swiss_design_lineage_vibecoding/style-guides/intermediate/NEO-BRUTALISM-GUIDE.html ; https://madegooddesigns.com/neobrutalism-web-design/

## 4. Linear-grade calm density [V]
Neutral near-black, tiny type, tight rows, very restrained accent. Theme comes from three variables (base, accent, contrast) in LCH so surfaces step evenly in perceived lightness.
- Type: Inter Display for headings, Inter for body (Linear's actual pairing).
- Palette (proposed): #0F1011 base, #16181A panel, #23262A border, #E6E8EB text, accent #7C5CFF.
- Interaction: command palette (Cmd-K) to jump to a device; list rows with 120ms hover; keyboard j/k through the lookups feed.
- Device web: small avatars in a force layout, edges only on hover. Heatmap: single-hue ramp for most; full heat ramp reserved for "anomalous" cells.
- Source: https://linear.app/now/how-we-redesigned-the-linear-ui

## 5. Bloomberg-terminal amber density [K]
Black field, amber/orange text, multi-pane, high info density, function-key style navigation.
- Type: JetBrains Mono or IBM Plex Mono 12px; condensed headings in Big Shoulders Display.
- Palette: #000, amber #FFA028, dim amber #8A5A14, cyan #3FC1FF, up #4AF626, down #FF433D, grid #2A2A2A.
- Interaction: ticker tape across the top streaming lookups; F-key row (F1 Devices, F2 Lookups, F3 Speed) at the bottom.
- Device web: ASCII/box-drawing tree. Heatmap: amber luminance ramp with character glyphs (. : o O @) as the non-colour cue.
- Source: https://www.bloomberg.com/company/stories/designing-the-terminal-for-color-accessibility/

## 6. Retro CRT / phosphor vector [V partial]
Scanlines and noise as a thin texture layer, phosphor green on black, pixel or bitmap type.
- Type: VT323 or Departure Mono (free) for body, Pixelify Sans for headline.
- Palette: phosphor #33FF66, dim #0F5A25, bg #050A06, amber alt #FFB000, paper alt #F4F0E6 / ink #111111.
- Interaction: a headline "types in" with a 40ms cursor; lookups flicker in with brief phosphor bloom (text-shadow 0 0 6px). Respect prefers-reduced-motion.
- Device web: vector lines on a radar sweep; devices blip when active. Heatmap: green intensity only, hot cells flash amber.
- Source: https://setproduct.com/blog/retro-brutalist-ui-design-2026

## 7. Editorial newsprint [K]
Cream paper, black ink, serif headline at huge size, column rules, small-caps datelines. Lookups feed reads like a ticker of classifieds.
- Type: Fraunces or Instrument Serif headline; Newsreader body; DM Mono for numbers.
- Palette: paper #F4F0E6, ink #111111, rule #BDB5A3, spot red #D7261E, blue #1B3A8C.
- Interaction: headline set as a front-page masthead ("OVERHEARD - Vol. 1, Sunday edition"); blocked items struck through with a red line animating left-to-right.
- Device web: hand-engraved-style node map, hairline black. Heatmap: halftone dots whose size encodes load, single red for peak.
- Reference style: Bloomberg Businessweek covers (see setproduct article). Source: https://setproduct.com/blog/retro-brutalist-ui-design-2026

## 8. Apple Fitness rings and bento [V]
Black surface, big rounded tiles in a bento grid, neon ring colours, one person per ring set. HIG: rings always on black, never recoloured, labels in matching colours (Move #FA114F, Exercise #A6FF00, Stand #00FFF6).
- Type: system SF (font-family: -apple-system, "Inter"), numerals at 48-64px bold.
- Palette: #000, tile #1C1C1E, neon red #FA114F, lime #A6FF00, cyan #00FFF6.
- Interaction: per-device ring = blocked / lookups / data vs. daily norm; rings animate fill on load with ease-out 800ms. Speed-test gauge reuses the ring form.
- Device web: a ring of avatars each wrapped in its own mini-ring. Heatmap: capsule-shaped cells in the ring colours.
- Note: HIG says rings are for one person only; a per-device ring is consistent with that, a combined one is not.
- Sources: https://developer.apple.com/design/human-interface-guidelines/activity-rings ; bento guide https://www.saasframe.io/blog/designing-bento-grids-that-actually-work-a-2026-practical-guide

## 9. Glass / Liquid-glass layer [K]
Translucent blurred panels over a colourful moving backdrop. Apple's Liquid Glass and Linear's own take show the trend; the common critique is low text contrast over busy backgrounds.
- Type: SF / Inter, medium weight to survive blur.
- Palette: backdrop gradient #0A1030 > #2B0A4F, glass rgba(255,255,255,0.08) with 1px rgba(255,255,255,0.18) border, text #FFFFFF at >=90%.
- Interaction: panels refract on hover (backdrop-filter saturate); headline pins in a pill.
- Device web: floating glass bubbles sized by traffic. Heatmap: cells opaque (glass hurts ramp legibility).
- Rule: put numbers on a solid scrim; glass only for chrome. Source: https://linear.app/blog/linear-liquid-glass

## 10. Vercel / Geist monochrome-technical [K]
Black and white with 1px borders, mono details, near-zero colour except status dots. Very developer-core.
- Type: Geist Sans + Geist Mono (Google Fonts).
- Palette: #000, #0A0A0A card, #333 border, #EDEDED text, status blue #0070F3, red #E5484D, green #46A758.
- Interaction: skeleton shimmer for loading, status dots with pulse for live devices, tabs with sliding underline.
- Device web: monochrome graph, selected node glows blue. Heatmap: grayscale with ramp only on legend hover.
- Source: https://vercel.com/geist/introduction

## 11. Raycast / Arc gradient-chrome [K]
Dark panel with soft gradient glow, icon-first, keyboard UI, playful gradient accents per space/profile.
- Type: Inter + SF Mono; headline in Bricolage Grotesque for character.
- Palette: #121212, #1C1C1E, gradient #FF6363>#FF9A3D, secondary #5B8CFF>#9B6BFF.
- Interaction: each device gets its own gradient "space" colour used consistently across web, lanes, and heatmap; spring transition when switching.
- Device web: gradient orbs. Heatmap: per-device hue ramp (light to saturated) instead of shared heat ramp.
- Sources: https://www.raycast.com ; https://arc.net

## 12. Things 3 soft, paper-light [K]
Light surface, extreme restraint, generous whitespace, tiny motion polish. A calm anti-dashboard.
- Type: SF / Manrope; numerals tabular.
- Palette: #FFFFFF, #F4F5F7, text #1D1D1F, accent blue #1E6BFF, muted #8E8E93.
- Interaction: rows checkoff-style: blocked lookups slide away with a soft spring; magic "plus" to add devices.
- Device web: list-first, web optional. Heatmap: tinted single-hue cells.
- Source: https://culturedcode.com/things/

## 13. Stripe-style gradient data product [K]
Clean charts on white or deep navy, precise alignment, diagonal gradient hero, perceptual colour.
- Type: Inter / Söhne-alike (Instrument Sans); tabular numerals.
- Palette: navy #0A2540, indigo #635BFF, cyan #00D4FF, mint #3ECF8E, #F6F9FC.
- Interaction: hover crosshair with synced tooltips across the lanes; numbers count up with tabular figures to prevent jitter.
- Device web: indigo edges on navy. Heatmap: perceptually uniform ramp (see Stripe's colour post).
- Source: https://stripe.com/blog/accessible-color-systems

## 14. Pi-hole / NextDNS / AdGuard Home reality-check [K]
These are the baseline to beat. Pi-hole: AdminLTE tiles with coloured icons and top-lists. NextDNS: clean white cards, one big "queries blocked" count with a sparkline and log tabs. AdGuard Home: green-accented Material-ish cards with a donut of upstreams. All are table-heavy and generic; none have per-device behaviour maps.
- What to steal: NextDNS's one-number-per-card clarity and log filters; Pi-hole's long-lived query log; AdGuard's per-client tab.
- What to avoid: stock coloured-icon tiles and donut charts.
- Sources: https://pi-hole.net ; https://nextdns.io ; https://adguard.com/kb/adguard-home/overview/

(Optional, hardware flavour: Ableton Push / OP-1 style screens use a few bright primaries on black with chunky icon labels; https://www.ableton.com/en/push/ )

---

## Shortlist for Overheard (my read, not a research finding)
Best match to "distinctive, bold type, bright accent on dark, product-grade": #1 (dot-matrix, echoes the board's LED matrix), #8 (bento + rings, already close to current look), #2 (instrument panel). #6 and #7 are the most unusual but need the most care for legibility.

---

## Five cross-cutting best practices

1. **3:1 for every data mark, plus gaps between cells.** WCAG 1.4.11 requires graphical objects to reach 3:1 against the surface; GitLab verified every step of its palette at 3:1 on its dark surface, and notes adjacent colours need not hit 3:1 against each other so it separates elements with a 1px gap in the surface colour. Apply to heatmap cells and device-web nodes. Sources: https://design.gitlab.com/data-visualization/color ; Smashing (added whitespace between heatmap tiles) https://smashingmagazine.com/2022/07/accessibility-first-approach-chart-visual-design/

2. **Do not rely on colour alone.** Add a second encoding (Smashing used box height; also glyphs, numbers on hover, text callouts of spikes) and keep any added marker subtle, since testers misread extra patterns as metrics. A blue>red ramp still needs a numeric legend. Same sources as above.

3. **Dark-mode sequential ramps get lighter as values rise.** GitLab's dark UI runs steps 500 (low) to 50 (high), so higher values are lighter, and its diverging scales get lighter toward each end. Your blue>cyan>green>yellow>orange>red ramp is multi-hue, which helps colourblind readers (GitLab recommends alternating hue and step), but keep lightness monotonic low-to-high so the red end does not read darker than the blue end. Avoid green and red as the only pair for good/bad; GitLab pairs green with magenta. Source: https://design.gitlab.com/data-visualization/color

4. **Build colour in a perceptually uniform space and drive themes from few variables.** Linear moved to LCH so equal lightness looks equal, and reduced a theme to base, accent and contrast (3 variables vs 98). Generate the heat ramp and the card elevation steps from the same system (e.g. OKLCH in CSS) and offer a contrast setting. Source: https://linear.app/now/how-we-redesigned-the-linear-ui

5. **Motion and density: purposeful, short, and reducible.** TE-style 100ms state changes and bouncing meters show feedback can be fast and tied to real events (a lookup arrives = a meter moves); gate all looping or entrance animation behind `prefers-reduced-motion` (MDN page not fetchable here: https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion). For density, Linear's lesson is hierarchy over decoration: reduce visual noise, align labels and icons on both axes, and test condensed vs spacious layouts; keep the chart usable at 200% zoom without scrolling (Smashing). Use tabular numerals so live-updating figures do not jitter.

Gaps: no source for Tailscale admin, Things, Arc, Raycast or Vercel pages was fetched; their entries are directional. Apple's rings rule (one person per ring set) came from the HIG page.
