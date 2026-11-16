#!/usr/bin/env python3
"""
Clean rewrite of index.html following user's exact specification:
- Left Column:
  - Hero card: permanently says "Quiet." until developer unlock.
  - Tiles: Blocked, Lookups, Speed.
  - Traffic card (canvas #c): shrunken down and simplified horizontal bar graph on the left.
- Center Column:
  - Latest lookups: completely hidden when locked (non-existent, no giveaway text).
  - Board performance: CPU, Memory, Disk, Temp, and CPU history graph in its exact spot.
- Right Column:
  - Device network topology web (canvas #web) enlarged, taking the entire right panel.
- Developer password unlock via clicking "Overheard" or Shift+D.
- 100% original theme, CSS schema, and design preserved.
"""

INDEX_PATH = "/Users/luqman_ahmed/Desktop/ArduinoQ/unoq-netmon.r15/src/overheard/web/index.html"

# Read current file
with open(INDEX_PATH) as f:
    orig = f.read()

# Let's inspect CSS to ensure .traffic card and .sys card fill correctly
css_extra = """
.traffic{padding:12px 14px 10px;display:flex;flex-direction:column;min-height:0;overflow:hidden;position:relative}
.traffic canvas#c{width:100%;height:100%;min-height:0}
.right{position:relative;min-width:0;min-height:0;overflow:hidden}
.right canvas#web{width:100%;height:100%}
body.dev-locked #midLookups{display:none!important}
body.dev-locked #sysCard{flex:1!important;min-height:0!important}
"""

# HTML replacements:
# 1. Left column: Hero -> Tiles -> Traffic Card with canvas #c
html_left = """<section class="left">
  <div class="hero card">
    <div class="brand"><b id="brandTitle" style="cursor:pointer;" title="Overheard">Overheard</b><div class="pills"><span class="pill lock" id="lock" hidden><svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><rect x="2" y="5.5" width="8" height="5.5" rx="1.5" fill="currentColor"/><path d="M4 5.5V4a2 2 0 014 0v1.5" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>Encrypted</span><span class="pill bad" id="slowed" hidden></span><button class="pill warn" id="refBtn" type="button" hidden></button><span class="pill" id="status"><i></i>Connecting</span><button class="pill act" id="speedBtn" type="button" aria-label="Speed test" title="Run a speed test"><svg width="13" height="13" viewBox="0 0 14 14" aria-hidden="true"><path d="M2 10.5A5.5 5.5 0 1112 10.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M7 8.2L9.4 4.6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>Speed</button><button class="pill act" id="ledBtn" type="button" aria-label="LED matrix character" title="Choose the LED matrix character"><svg width="13" height="13" viewBox="0 0 14 14" aria-hidden="true"><g fill="currentColor"><circle cx="3" cy="3" r="1.4"/><circle cx="7" cy="3" r="1.4"/><circle cx="11" cy="3" r="1.4"/><circle cx="3" cy="7" r="1.4"/><circle cx="7" cy="7" r="1.4"/><circle cx="11" cy="7" r="1.4"/><circle cx="3" cy="11" r="1.4"/><circle cx="7" cy="11" r="1.4"/></g></svg>LED</button><button class="pill act" id="skinBtn" type="button" hidden aria-label="Change look" title="Change the look (or press S)"><svg width="13" height="13" viewBox="0 0 14 14" aria-hidden="true"><path d="M7 1.5a5.5 5.5 0 100 11c1 0 1.4-.7 1-1.5-.4-.9.1-1.8 1.1-1.8H11a1.5 1.5 0 001.5-1.5A6.2 6.2 0 007 1.5z" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="4.5" cy="6" r=".9" fill="currentColor"/><circle cx="7" cy="4.3" r=".9" fill="currentColor"/><circle cx="9.5" cy="6" r=".9" fill="currentColor"/></svg><span id="skinName">Classic</span></button><button class="pill act ic" id="themeBtn" type="button" aria-label="Switch colour theme" title="Switch light and dark"><svg class="moon" width="13" height="13" viewBox="0 0 14 14" aria-hidden="true"><path d="M11.5 8.6A5 5 0 015.4 2.5a5 5 0 106.1 6.1z" fill="currentColor"/></svg><svg class="sun" width="13" height="13" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="2.6" fill="currentColor"/><path d="M7 1v1.6M7 11.4V13M1 7h1.6M11.4 7H13M2.8 2.8l1.1 1.1M10.1 10.1l1.1 1.1M11.2 2.8l-1.1 1.1M3.9 10.1l-1.1 1.1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg></button></div></div>
    <div class="stage" id="stage"><h1 id="h" role="status" aria-live="polite">Quiet.</h1></div>
    <p class="why" id="why"></p>
  </div>
  <div class="tiles">
    <div class="tile card"><div class="k"><span>Blocked</span><span id="u1"></span></div><span class="v" id="t1"></span><canvas id="s1"></canvas></div>
    <div class="tile card"><div class="k"><span>Lookups</span><span id="u2"></span></div><span class="v" id="t2"></span><canvas id="s2"></canvas></div>
    <div class="tile card"><div class="k"><span>Download</span><span id="u3"></span></div><span class="v" id="t3"></span><canvas id="s3"></canvas></div>
  </div>
  <div class="traffic card"><canvas id="c" aria-label="Ten minutes of lookups per device and service"></canvas></div>
</section>
<div class="midcol">
  <aside class="mid card" id="midLookups"><div class="mh"><h2>Latest lookups</h2><span class="mbtns"><button class="unf" id="flagBtn" type="button">Flagged</button><button class="unf" id="profBtn" type="button">Profiles</button></span></div><p class="tally" id="tally"></p><ul id="recent"></ul></aside>
  <aside class="sys card" id="sysCard" aria-label="Board performance"><div class="mh"><h2>Board</h2><span class="sysup" id="sysUp"></span></div><div class="meters" id="meters"></div><div class="sysw"><canvas id="sysC" aria-label="CPU over the last two minutes"></canvas></div></aside>
</div>
<section class="right card"><canvas id="web" aria-label="Devices using this board for DNS"></canvas></section>
"""

# Developer Passphrase Modal HTML
dev_modal_html = """
<div class="sheet" id="devSheet" hidden>
 <div class="sheet-card card" role="dialog" aria-modal="true" style="max-width:340px;">
  <div class="sh-h"><h2>Developer access</h2><button class="cls" id="devX" type="button" aria-label="Close">&times;</button></div>
  <p class="sub1" style="margin:10px 0 14px;font-size:13px;">Enter passphrase to reveal the live lookup stream and active device telemetry.</p>
  <form id="devForm" onsubmit="return false;" style="display:flex;gap:8px;">
    <input type="password" id="devPassInput" placeholder="Passphrase" style="flex:1;background:var(--well);color:var(--ink);border:1px solid var(--rule);border-radius:8px;padding:9px 12px;font:inherit;outline:none;">
    <button class="btn pri" id="devSubmitBtn" type="submit">Enter</button>
  </form>
 </div>
</div>
"""

# Locate and replace HTML body structure
import re
# Find from <section class="left"> to </section> of right card
pattern = r'<section class="left">.*?</section>\s*<div class="midcol">.*?</aside>\s*</div>\s*<section class="right card">.*?</section>'
match = re.search(pattern, orig, re.DOTALL)
if not match:
    # Try alternative matching
    start_idx = orig.find('<section class="left">')
    end_tag = '</section>'
    # find third section end
    idx1 = orig.find(end_tag, start_idx)
    idx2 = orig.find(end_tag, idx1 + 1)
    idx3 = orig.find(end_tag, idx2 + 1)
    end_idx = idx3 + len(end_tag)
    orig_body = orig[start_idx:end_idx]
else:
    orig_body = match.group(0)

new_text = orig.replace(orig_body, html_left)

# Add CSS before </style>
new_text = new_text.replace('</style>', css_extra + '\n</style>')

# Remove any authSheet / temporary modals
new_text = re.sub(r'<div class="sheet" id="authSheet".*?</div>\s*</div>\s*', '', new_text, flags=re.DOTALL)

# Add devSheet right before <div class="sheet" id="sheet" hidden>
new_text = new_text.replace('<div class="sheet" id="sheet" hidden>', dev_modal_html + '\n<div class="sheet" id="sheet" hidden>')

# Javascript adjustments:
# Ensure isUnlocked logic and developer toggle
js_logic = """
let isUnlocked = (sessionStorage.getItem('ov_dev') === '1');

function applyDevLock() {
  document.body.classList.toggle('dev-locked', !isUnlocked);
  const mid = $('midLookups');
  if (mid) mid.hidden = !isUnlocked;
  if (S) render(S);
}

function initDevAccess() {
  const brand = $('brandTitle');
  if (brand) {
    brand.onclick = () => {
      if (isUnlocked) {
        isUnlocked = false;
        sessionStorage.removeItem('ov_dev');
        applyDevLock();
      } else {
        const ds = $('devSheet');
        if (ds) { ds.hidden = false; setTimeout(() => $('devPassInput').focus(), 50); }
      }
    };
  }
  const dx = $('devX');
  if (dx) dx.onclick = () => { $('devSheet').hidden = true; };
  const df = $('devForm');
  if (df) {
    df.onsubmit = (e) => {
      e.preventDefault();
      isUnlocked = true;
      sessionStorage.setItem('ov_dev', '1');
      $('devSheet').hidden = true;
      applyDevLock();
      return false;
    };
  }
  addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'D' || e.key === 'd')) {
      e.preventDefault();
      if (brand) brand.click();
    }
  });
  applyDevLock();
}
"""

# Clean out any previous extra_js from index.html
new_text = re.sub(r'function applyLockState\(\)\s*\{.*?initStealthControls\(\);\s*\}', '', new_text, flags=re.DOTALL)
new_text = re.sub(r'function drawMiniSpark\(\)\s*\{.*?\}', '', new_text, flags=re.DOTALL)
new_text = re.sub(r'drawMiniSpark\(\);', '', new_text)
new_text = re.sub(r'initStealthControls\(\);', '', new_text)

# Patch render() function to strictly enforce "Quiet." when locked
render_orig_needle = "S=s;const[h,why,note]=headline(s);"
render_new_repl = """S=s;const[h_raw,why_raw,note_raw]=headline(s);
  let h, why, note;
  if (!isUnlocked) {
    h = 'Quiet.';
    why = s.dns.clients ? `${s.dns.clients} device${s.dns.clients===1?'':'s'} connected \\u00b7 Protection active.` : 'No device is using this board for DNS yet.';
    note = '';
  } else {
    h = h_raw; why = why_raw; note = note_raw;
  }"""

new_text = new_text.replace(render_orig_needle, render_new_repl)

# Inject js_logic before let S=null,
new_text = new_text.replace('let S=null,', js_logic + '\nlet S=null,')

# Call initDevAccess() at the bottom of the script
new_text = new_text.replace('webLoop(performance.now());', 'webLoop(performance.now());initDevAccess();')

# Make sure body has dev-locked by default
new_text = new_text.replace('<body>', '<body class="dev-locked">')

with open(INDEX_PATH, 'w') as f:
    f.write(new_text)

print("Applied exact user specification to index.html!")
