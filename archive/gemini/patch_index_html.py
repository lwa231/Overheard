"""Patch index.html to create the new default stealth/locked view."""

with open('/Users/luqman_ahmed/Desktop/ArduinoQ/unoq-netmon.r15/src/overheard/web/index.html') as f:
    text = f.read()

# 1. Hide skin button for now
text = text.replace('id="skinBtn" type="button"', 'id="skinBtn" type="button" hidden')

# 2. Add lock button to brand pills
brand_needle = '<div class="pills"><span class="pill lock" id="lock" hidden>'
brand_repl = '<div class="pills"><button class="pill lock" id="lockPill" type="button" title="Stealth Mode (Click to unlock)"><svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><rect x="2" y="5.5" width="8" height="5.5" rx="1.5" fill="currentColor"/><path d="M4 5.5V4a2 2 0 014 0v1.5" fill="none" stroke="currentColor" stroke-width="1.4"/></svg><span id="lockPillLabel">Locked</span></button><span class="pill lock" id="lock" hidden>'
text = text.replace(brand_needle, brand_repl)

# 3. Replace web card on left with mini card
web_left = '<div class="web card"><canvas id="web" aria-label="Devices using this board for DNS"></canvas></div>'
mini_left = '<div class="mini card"><div class="mh"><h2>Activity</h2><span class="pill" id="miniPill">Protected</span></div><div class="mini-body"><canvas id="miniSpark" style="width:100%;height:100%;"></canvas></div></div>'
text = text.replace(web_left, mini_left)

# 4. Put web card into right card, enlarged
right_needle = '<section class="right card"><canvas id="c" aria-label="Ten minutes of lookups per device and service"></canvas></section>'
right_repl = '<section class="right card"><div class="mh" style="position:absolute;top:16px;left:20px;z-index:2;pointer-events:none;"><h2>Device network topology</h2></div><canvas id="web" aria-label="Devices using this board for DNS" style="position:absolute;top:0;left:0;width:100%;height:100%;"></canvas><canvas id="c" aria-label="Ten minutes of lookups per device and service" hidden></canvas></section>'
text = text.replace(right_needle, right_repl)

# 5. Add stealth shield to mid card (Latest lookups)
mid_needle = '<p class="tally" id="tally"></p><ul id="recent"></ul>'
mid_repl = '<div id="midShield" style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;color:var(--ink-2);text-align:center;padding:24px 12px;"><svg width="24" height="24" viewBox="0 0 12 12" fill="currentColor" style="opacity:0.4"><rect x="2" y="5.5" width="8" height="5.5" rx="1.5"/><path d="M4 5.5V4a2 2 0 014 0v1.5" fill="none" stroke="currentColor" stroke-width="1.4"/></svg><span style="font-size:13px;">Live lookup stream protected</span><button class="pill lock" id="unlockMidBtn" type="button" style="cursor:pointer;">Unlock</button></div><p class="tally" id="tally" hidden></p><ul id="recent" hidden></ul>'
text = text.replace(mid_needle, mid_repl)

# 6. Add mini card CSS
css_needle = '.right{position:relative;min-width:0;min-height:0}'
css_repl = '.mini{padding:16px 20px 14px;display:flex;flex-direction:column;min-height:0;overflow:hidden}.mini-body{flex:1;position:relative;width:100%;min-height:0}.right{position:relative;min-width:0;min-height:0}'
text = text.replace(css_needle, css_repl)

# 7. Add auth modal HTML right before the other sheets
auth_sheet_html = '''
<div class="sheet" id="authSheet" hidden>
 <div class="sheet-card card" role="dialog" aria-modal="true" aria-labelledby="auth-t" style="max-width:360px;">
  <div class="sh-h"><h2 id="auth-t">Unlock Stream</h2><button class="cls" id="authX" type="button" aria-label="Close">&times;</button></div>
  <p class="sub1" style="margin:12px 0 16px;font-size:13px;">Enter passphrase to reveal the live lookup stream and active device detection.</p>
  <form id="authForm" onsubmit="return false;" style="display:flex;gap:8px;">
    <input type="password" id="authKeyInput" placeholder="Passphrase" style="flex:1;background:var(--well);color:var(--ink);border:1px solid var(--rule);border-radius:8px;padding:9px 12px;font:inherit;outline:none;">
    <button class="btn pri" id="authSubmit" type="submit">Unlock</button>
  </form>
 </div>
</div>
'''
text = text.replace('<div class="sheet" id="sheet" hidden>', auth_sheet_html + '\n<div class="sheet" id="sheet" hidden>')

# 8. JS hook for headline and lock state
js_needle = 'function headline(s){\nconst n=s.now,d=s.dns;'
js_repl = '''let isUnlocked = (sessionStorage.getItem('ov_unlocked') === '1');
function headline(s){
  if (!isUnlocked) {
    const d = s.dns;
    return ['Quiet.', d.clients ? `${d.clients} device${d.clients === 1 ? '' : 's'} connected \\u00b7 Protection active.` : 'No device is using this board for DNS yet.', ''];
  }
  const n = s.now, d = s.dns;'''
text = text.replace(js_needle, js_repl)

# 9. Extra JS functions for applyLockState and handlers
extra_js = '''
function applyLockState() {
  const p = $('lockPill'), pl = $('lockPillLabel'), ms = $('midShield'), r = $('recent'), t = $('tally');
  if (isUnlocked) {
    if (p) p.className = 'pill act';
    if (pl) pl.textContent = 'Unlocked';
    if (ms) ms.hidden = true;
    if (r) r.hidden = false;
    if (t) t.hidden = false;
  } else {
    if (p) p.className = 'pill lock';
    if (pl) pl.textContent = 'Locked';
    if (ms) ms.hidden = false;
    if (r) r.hidden = true;
    if (t) t.hidden = true;
  }
  if (S) render(S);
}

function drawMiniSpark() {
  const cv = $('miniSpark'); if (!cv || !S) return;
  const [x, W, H] = size(cv);
  x.clearRect(0, 0, W, H);
  const rows = S.devices || [];
  if (!rows.length) return;
  const vals = rows.map(d => d.rate || 0);
  const max = Math.max(1, ...vals);
  x.strokeStyle = 'rgba(154, 139, 255, 0.8)';
  x.lineWidth = 2.5;
  x.beginPath();
  vals.forEach((v, i) => {
    const px = (i / Math.max(1, vals.length - 1)) * (W - 16) + 8;
    const py = H - (v / max) * (H - 20) - 10;
    if (i === 0) x.moveTo(px, py); else x.lineTo(px, py);
  });
  x.stroke();
}

function initStealthControls() {
  const p = $('lockPill');
  if (p) p.onclick = () => {
    if (isUnlocked) {
      isUnlocked = false;
      sessionStorage.removeItem('ov_unlocked');
      applyLockState();
    } else {
      $('authSheet').hidden = false;
      setTimeout(() => $('authKeyInput').focus(), 50);
    }
  };
  const midUnlock = $('unlockMidBtn');
  if (midUnlock) midUnlock.onclick = () => { $('authSheet').hidden = false; setTimeout(() => $('authKeyInput').focus(), 50); };
  const ax = $('authX');
  if (ax) ax.onclick = () => { $('authSheet').hidden = true; };
  const af = $('authForm');
  if (af) af.onsubmit = (e) => {
    e.preventDefault();
    isUnlocked = true;
    sessionStorage.setItem('ov_unlocked', '1');
    $('authSheet').hidden = true;
    applyLockState();
    return false;
  };
  applyLockState();
}
'''

text = text.replace('let S=null,', extra_js + '\nlet S=null,')

# Hook initStealthControls and drawMiniSpark into render loop
text = text.replace('fitHeadline();drawWeb();drawTable();', 'fitHeadline();drawWeb();drawTable();drawMiniSpark();')
text = text.replace('webLoop(performance.now());', 'webLoop(performance.now());initStealthControls();')

with open('/Users/luqman_ahmed/Desktop/ArduinoQ/unoq-netmon.r15/src/overheard/web/index.html', 'w') as f:
    f.write(text)

print('Successfully patched index.html with authentic Overheard theme!')
