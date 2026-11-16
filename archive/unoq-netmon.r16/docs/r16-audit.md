# r16 audit: what Gemini changed in r15

Method: file mtimes after 2026-11-09 20:40 UTC (11 files, matches the list). No pre-Gemini copy exists here, so
"changed" is inferred from contradictions with tests, docs and the r15 handoff. No tests were touched (all mtimes 11-09 15:31).

## CI (`make ci` stops at the first stage, so each stage was also run alone)
- ruff: FAIL, 46 errors (27 in src: adstream.py 22, live_capture.py 5; 19 in experimental/_incoming, staged by us, not Gemini).
  Causes: typing.Dict/List/Optional instead of builtins (UP006/UP035/UP045), unused imports (F401), unused loop var (B007).
- sprite check: PASS.
- pytest: 101 passed, 6 failed (107 total, same count as the r15 handoff).
  1 test_adult::test_slowdown_applies_only_to_the_tripped_device_and_ends: slow_down() is a stub that returns True.
  2 test_adult::test_slowed_queries_are_dropped_not_queued_forever: same stub, never drops.
  3 test_network::test_slowed_device_really_waits: same stub, 0 s delay instead of >= 0.25 s.
  4 test_fingerprint::test_android_and_mac_and_tv: swscan/gsa.apple.com now "Apple device", test wants "Mac".
  5 test_safesearch::test_targets: target() ignores youtube=True, returns None.
  6 test_security::test_safesearch_covers_country_google_and_youtube_names: same (music.youtube.com).
- smoke: PASS ("4 devices"). It never loads index.html, so it cannot see the dashboard breakage below.

## Per file
### web/index.html (worst)
- BROKEN: the main script no longer parses. Two SyntaxErrors: an orphan `);  x.stroke(); }` right after applyLockState()
  (file lines ~284-286, the tail of a function whose head was overwritten), and a doubled `}` closing initDevAccess() (~line 378).
- BROKEN: the code between esc() and applyLockState() was overwritten. `render`, `S`, `RM` and `setFocus` are no longer
  defined anywhere, yet are used (tick(), drawGate(), resize handler, row click). Even after fixing syntax, the first run
  throws `RM is not defined`. Result: the dashboard is a blank shell; no tiles, web, table, speed test, LED sheet,
  profiles, themeBtn or skinBtn handlers (all live in the same script).
- DEAD: neither initStealthControls() nor initDevAccess() is ever called. P key, brand-click login and the lock are unreachable.
- Two competing lock systems: initStealthControls (sessionStorage `ov_unlocked`, ids lockPill, lockPillLabel, midShield,
  authSheet, authForm, authKeyInput, authX, unlockMidBtn: none exist in the HTML) and initDevAccess (`ov_dev`, #devSheet).
  Both write one shared `isUnlocked`, declared once (line ~317) and reading only `ov_dev`.
- INSECURE/theatre: see answer (a). Hiding the DOM is not access control; the token cookie is the only real gate.
- Style: ~110 lines of spaced 2-indent code with `function name() {` blocks among minified one-liners; inline `style=`
  on the new sheet (fixed `monospace`, `border-radius:8px`, `max-width:360px`) bypasses skin variables.
- Misleading UI copy: "Arduino Uno Q - System Login ... Authenticate with board password" for a field that checks nothing.

### dnsserver.py
- DEAD: slow_down() body commented out under "DISABLED ... for review"; always returns True. The adult-guard slowdown
  (core r15 feature) is off; `_slow_slots` unused. Blocking of listed adult domains still works.
- INCONSISTENT: Guard.summary()/penalty box still trip, `/api/stats.adult.slowed` still lists "slowed" devices and the UI
  shows a red "slowed" pill while nothing is slowed. adult.py docstring and handoff still promise the slowdown. 3 tests fail.
- Style: commented-out code and "uncomment to re-enable" notes; the codebase otherwise has none.

### fingerprint.py
- PATCHED-IN: Mac-specific rule folded into "Apple device" (comment says iPhones hit swscan; swscan/swdist are macOS
  update hosts, so this loses signal). Breaks test #4. `NOTES` dict added, never used.

### safesearch.py
- BROKEN/DEAD: `youtube` argument accepted but ignored; YouTube Restricted Mode mapping removed. `--youtube-restricted`
  (config.py, dnsserver.py) is now a silent no-op. Breaks tests #5, #6.

### adult.py
- INCONSISTENT: NEVER_FLAG is much wider than the handoff states (adds google.com, googleapis.com, gstatic.com,
  amazonaws.com, cloudfront.net, cdn.cloudflare.net, github.io, akamaihd.net, youtube.com, googlevideo.com, ytimg.com, ggpht.com, youtu.be).
  It is checked before the list, so a listed domain under those suffixes is never flagged (see answer d).
- Guard.summary() reports "enabled": True although the slowdown is stubbed.

### blocklist.py
- PATCHED-IN: BUILTIN_AD_DOMAINS (14 hosts) merged into every Blocklist; mostly redundant with the downloaded list (not checked offline). `s.youtube.com` is YouTube's playback-stats host: blocking it risks watch-history and some
  TV/app playback problems. In-stream YouTube ads are served from googlevideo.com; DNS cannot block them.

### config.py
- INSECURE/INCONSISTENT: default `allow` now ends with `203.0.113.0/24`: the owner's building NAT /24 (256 public
  addresses) hard-coded as a permanent default, not opt-in. Handoff and tests assume `--allow-extra 203.0.113.254/32`
  as an explicit opt-in. Widens the resolver to other tenants behind that NAT pool and leaks a personal address into source.

### scripts/install.sh and Install Overheard.command
- INSECURE/INCONSISTENT: `ALLOW_EXTRA` defaults to `203.0.113.0/24` in both files (duplicated defaults, and again in
  config.py). `${ALLOW_EXTRA:-...}` means an empty value cannot clear it; `none` is not implemented.
- PRIVACY: `NO_TLS` defaults to 1, so every install adds `--no-tls`: upstream DNS goes out in plaintext UDP. This contradicts
  README/security.md ("DoT upstream", "fail closed"). Not mentioned in the installer's output.
- Positive: the character whitelist on ALLOW_EXTRA still protects the heredoc from injection.

### adstream.py (599 lines, new)
- DEAD: imported by nothing, no tests, no docs link. Needs `netfilterqueue` (breaks the stdlib-only rule) and an iptables
  FORWARD hook, but the board is a DNS server, not the gateway, so it would see no client traffic.
- BROKEN regexes: `^\.doubleclick\.net$` can never match; `redirector.googlevideo.com` is dropped though it is a
  normal video redirector (comment claims "never serves video"). `s.youtube.com` dropped by SNI rule and again in Phase 4.
- Fabricated-looking JA3 hashes (`d4e5b18d7c9d8b4c5e6f7a8b9c0d1e2f` is a counting pattern).
- `_flows` is a defaultdict keyed per direction, GC every 60 s only: unbounded growth under a flood; key comment says
  "canonical client->server" but it is not. Logs a line per allowed flow.
- Style: typing.Dict/List/Optional, banner comments, long prose docstring, `-> bool` hints; unlike the rest of the code.

### live_capture.py (254 lines, new)
- DEAD: standalone root-only AF_PACKET sniffer, not wired in. Copies AD_SNI_PATTERNS from adstream (with the pattern
  differing: `\.doubleclick\.net$` here vs the broken `^\.` there). Unused imports (ipaddress, defaultdict), unused loop var.
  `experimental/_incoming/live_youtube_traffic.py` is a 508-diff-line sibling of the same idea (not run);
  `dpi_packet_filter.py` is a non-functional "SSL decryption" skeleton (not run).

## Answers
(a) P-key password: client-side only, no server call, and not even a check. Quote (initDevAccess):
    `if (inp && inp.value.trim().length > 0) { isUnlocked = true; sessionStorage.setItem('ov_dev','1'); ...}`
    Any non-empty string "unlocks"; flag lives in sessionStorage (devtools can set it). Currently unreachable anyway.
(b) Yes. server.py serves /api/stats (24 recent lookups with client IP + domain, per-device rows, adult summary) and
    /api/flagged to any holder of the access token; the lock never reaches the server (stats.py/server.py untouched).
(c) Skins: skins.css/skins.js only need `:root[data-skin]`, `.card`, `.tile .v`, `.sheet-card`, h1 and variables; those
    remain. What broke: the script does not run, so skinBtn/themeBtn/nextSkin and all drawing are dead; shots.py
    clicks #ledBtn and #profBtn (elements exist, handlers do not); new login sheet uses hard-coded radius/monospace/
    max-width inline styles; `body.dev-locked #midLookups{display:none!important}` and `#sysCard{flex:1!important}` would
    override skin layouts if the lock were ever applied; the old `#lock` "Encrypted" pill is orphaned. The 3-column
    layout (.left / .midcol / .right), tile ids t1-t3/s1-s3 and card classes are intact. ui-research.md has no id contract.
(d) Mixed. Name rules: TLD in {xxx, porn, sex, adult}; any non-TLD label equal to `sex` or `xxx`; any label containing
    porn, hentai, xvideo, xnxx, xhamster, redtube, youporn, onlyfans, camgirl, chaturbate, stripchat, livejasmin,
    bangbros, brazzers. Tested false positives: pornichet.fr, pornic.fr (French towns), sex.ed.gov, sex.com, onlyfans.com
    (by design), porn.stackexchange-style research sites. essex/sussex are safe. Bigger issue is false negatives: NEVER_FLAG
    exempts whole suffixes, so adult content on *.github.io, *.cloudfront.net, *.cdn.cloudflare.net, sites.google.com, *.googlevideo.com is never flagged.
(e) No tests added, changed or deleted (mtimes unchanged, 107 tests as in the handoff). Gemini changed behaviour without
    updating tests: 6 now fail.

## Top fixes for r16
1. Repair index.html (restore render/S/RM/setFocus and the overwritten block; remove the two stray fragments).
2. Remove the fake System Login (both lock systems) or make it a real server-checked gate.
3. Restore slow_down() or deliberately drop the feature everywhere (tests, UI, docs).
4. Revert 203.0.113.0/24 defaults (config, install.sh, .command) to the opt-in /32; fix `--no-tls` default.
5. Restore the YouTube/Mac behaviours or update tests; delete or quarantine adstream.py/live_capture.py.
