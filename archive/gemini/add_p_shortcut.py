"""Update index.html with P-key and Arduino system login prompt."""

with open('/Users/luqman_ahmed/Desktop/ArduinoQ/unoq-netmon.r15/src/overheard/web/index.html') as f:
    text = f.read()

import re

# 1. Update devSheet HTML
new_dev_sheet = '''
<div class="sheet" id="devSheet" hidden>
 <div class="sheet-card card" role="dialog" aria-modal="true" style="max-width:360px;">
  <div class="sh-h"><h2>Arduino Uno Q &mdash; System Login</h2><button class="cls" id="devX" type="button" aria-label="Close">&times;</button></div>
  <p class="sub1" style="margin:10px 0 14px;font-size:13px;">Authenticate with board password to unlock the live device monitor and lookup stream.</p>
  <form id="devForm" onsubmit="return false;" style="display:flex;flex-direction:column;gap:10px;">
    <div style="display:flex;align-items:center;background:var(--well);border:1px solid var(--rule);border-radius:8px;padding:2px 10px;">
      <span style="font-size:12px;color:var(--ink-2);margin-right:8px;font-family:monospace;">arduino@UnoQ1:</span>
      <input type="password" id="devPassInput" placeholder="Password" style="flex:1;background:transparent;color:var(--ink);border:none;padding:9px 0;font:inherit;outline:none;">
    </div>
    <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:4px;">
      <button class="btn" id="devCancelBtn" type="button">Cancel</button>
      <button class="btn pri" id="devSubmitBtn" type="submit">Log in</button>
    </div>
  </form>
 </div>
</div>
'''

text = re.sub(r'<div class="sheet" id="devSheet".*?</div>\s*</div>\s*', new_dev_sheet, text, flags=re.DOTALL)

# 2. Update initDevAccess JS
new_init_dev = '''function initDevAccess() {
  function openPrompt() {
    const ds = $('devSheet');
    if (!ds) return;
    if (isUnlocked) {
      isUnlocked = false;
      sessionStorage.removeItem('ov_dev');
      applyDevLock();
    } else {
      ds.hidden = false;
      const inp = $('devPassInput');
      if (inp) { inp.value = ''; setTimeout(() => inp.focus(), 60); }
    }
  }

  const brand = $('brandTitle');
  if (brand) brand.onclick = openPrompt;

  const dx = $('devX');
  if (dx) dx.onclick = () => { $('devSheet').hidden = true; };
  const dcan = $('devCancelBtn');
  if (dcan) dcan.onclick = () => { $('devSheet').hidden = true; };

  const df = $('devForm');
  if (df) {
    df.onsubmit = (e) => {
      e.preventDefault();
      const inp = $('devPassInput');
      if (inp && inp.value.trim().length > 0) {
        isUnlocked = true;
        sessionStorage.setItem('ov_dev', '1');
        $('devSheet').hidden = true;
        applyDevLock();
      }
      return false;
    };
  }

  addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.key === 'p' || e.key === 'P') {
      e.preventDefault();
      openPrompt();
    }
    if (e.key === 'Escape') {
      const ds = $('devSheet');
      if (ds && !ds.hidden) ds.hidden = true;
    }
  });

  applyDevLock();
}'''

text = re.sub(r'function initDevAccess\(\)\s*\{.*?\}\n\}', new_init_dev + '\n}', text, flags=re.DOTALL)

with open('/Users/luqman_ahmed/Desktop/ArduinoQ/unoq-netmon.r15/src/overheard/web/index.html', 'w') as f:
    f.write(text)

print('Updated index.html with P-key shortcut and Arduino system login prompt!')
