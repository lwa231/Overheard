#!/usr/bin/env python3
"""
Generates the sandbox prototype for the new Stealth / Header view
and takes headless Chrome screenshots of both Locked and Unlocked states.
"""

import os
import subprocess
import time

ARTIFACT_DIR = "/Users/luqman_ahmed/.gemini/antigravity/brain/8b8d0671-a6c3-422b-9cfa-289d973f99c5"
SCRATCH_DIR = os.path.join(ARTIFACT_DIR, "scratch")
HTML_PATH = os.path.join(SCRATCH_DIR, "stealth_dashboard_preview.html")
CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

html_content = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Overheard — Network Monitor & Shield</title>
<style>
:root[data-theme=dark] {
  color-scheme: dark;
  --paper: #0B0E14;
  --card: #151922;
  --well: #1E2330;
  --accent: #7C67FE;
  --accent-ink: #9A8BFF;
  --accent-rgb: 154, 139, 255;
  --ink: #E9EDF4;
  --ink-2: rgba(233, 237, 244, 0.65);
  --rule: rgba(233, 237, 244, 0.12);
  --line: rgba(255, 255, 255, 0.08);
  --edge: rgba(255, 255, 255, 0.18);
  --ok-bg: rgba(70, 200, 125, 0.16);
  --ok: #7BE2A8;
  --warn-bg: rgba(255, 190, 70, 0.16);
  --warn: #FFCB6B;
  --lock-bg: rgba(140, 120, 255, 0.2);
  --lock: #BDB2FF;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--paper);
  color: var(--ink);
  font: 400 14px/1.4 var(--font);
  display: grid;
  grid-template-columns: minmax(380px, 1.1fr) 280px minmax(420px, 1.4fr);
  grid-template-rows: 100vh;
  gap: 14px;
  padding: 14px;
  overflow: hidden;
  height: 100vh;
}

.card {
  background: var(--card);
  border: 1px solid var(--rule);
  border-radius: 12px;
  position: relative;
  overflow: hidden;
}

/* ── LEFT COLUMN ── */
.col-left {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
}

.hero {
  padding: 20px 22px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.brand-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.brand-title {
  font-size: 19px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--ink);
  display: flex;
  align-items: center;
  gap: 8px;
}

.pills {
  display: flex;
  gap: 6px;
  align-items: center;
}

.pill {
  font-size: 11px;
  font-weight: 600;
  padding: 4px 9px;
  border-radius: 999px;
  background: var(--well);
  color: var(--ink-2);
  border: 1px solid var(--line);
  display: inline-flex;
  align-items: center;
  gap: 5px;
  cursor: pointer;
}
.pill.ok { background: var(--ok-bg); color: var(--ok); border-color: rgba(123, 226, 168, 0.3); }
.pill.lock-btn {
  background: var(--lock-bg);
  color: var(--lock);
  border-color: rgba(189, 178, 255, 0.4);
}

.stage h1 {
  font-size: 42px;
  font-weight: 800;
  letter-spacing: -0.04em;
  line-height: 1.05;
  color: var(--ink);
  transition: color 0.2s;
}

.stage.unlocked h1 {
  color: #7BE2A8;
}

.stage p.sub {
  font-size: 13px;
  color: var(--ink-2);
  margin-top: 4px;
}

.tiles {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.tile {
  background: var(--well);
  border-radius: 8px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.tile .label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--ink-2);
  font-weight: 600;
}

.tile .val {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

/* Small Sparkline Graphs where the web used to be */
.mini-graphs {
  flex: 1;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.mini-graph-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.mini-graph-header h3 {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-2);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.sparkline-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
  justify-content: center;
}

.spark-card {
  background: var(--well);
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.spark-info b { font-size: 15px; }
.spark-info span { font-size: 11px; color: var(--ink-2); display: block; }

/* ── MIDDLE COLUMN (BOARD VITALS) ── */
.col-mid {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.board-card {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.card-title {
  font-size: 14px;
  font-weight: 700;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.vitals-meter {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.meter-label {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--ink-2);
}

.meter-bar {
  height: 6px;
  background: var(--well);
  border-radius: 999px;
  overflow: hidden;
}

.meter-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 999px;
}

.lookup-card {
  flex: 1;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.stealth-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--ink-2);
  text-align: center;
  padding: 20px;
}

.stealth-placeholder svg {
  opacity: 0.4;
}

.lookup-stream {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 12px;
  overflow: hidden;
}

.lookup-item {
  display: flex;
  justify-content: space-between;
  padding: 6px 8px;
  background: var(--well);
  border-radius: 6px;
}

/* ── RIGHT COLUMN (ENLARGED DEVICE WEB) ── */
.col-right {
  display: flex;
  flex-direction: column;
  min-height: 0;
  position: relative;
}

.web-stage {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px 20px;
  position: relative;
}

.web-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  z-index: 2;
}

.web-header h2 {
  font-size: 15px;
  font-weight: 700;
}

.web-canvas-container {
  flex: 1;
  position: relative;
  width: 100%;
  height: 100%;
}

canvas#webCanvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}

/* ── PASSWORD MODAL OVERLAY ── */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal-card {
  width: 360px;
  background: #181C26;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 14px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
}

.modal-card h3 {
  font-size: 18px;
  font-weight: 700;
}

.modal-card p {
  font-size: 13px;
  color: var(--ink-2);
}

.pass-input {
  width: 100%;
  background: #0F131C;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  padding: 10px 14px;
  color: #fff;
  font-size: 14px;
  outline: none;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.btn {
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: none;
}
.btn-sec { background: var(--well); color: var(--ink); }
.btn-pri { background: var(--accent); color: #fff; }
</style>
</head>
<body>

<!-- LEFT COLUMN -->
<div class="col-left">
  <div class="card hero">
    <div class="brand-bar">
      <div class="brand-title">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
        Overheard
      </div>
      <div class="pills">
        <span class="pill ok">● Encrypted (DoT)</span>
        <span class="pill">3 devices</span>
        <button class="pill lock-btn" id="lockToggleBtn">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          <span id="lockStatusText">Locked</span>
        </button>
      </div>
    </div>

    <div class="stage" id="stageBanner">
      <h1 id="heroTitle">Quiet</h1>
      <p class="sub" id="heroSub">Network idle • All 3 devices shielded • Protection active</p>
    </div>

    <div class="tiles">
      <div class="tile">
        <span class="label">Blocked</span>
        <span class="val">1,492</span>
      </div>
      <div class="tile">
        <span class="label">Lookups</span>
        <span class="val">28.4k</span>
      </div>
      <div class="tile">
        <span class="label">Speed</span>
        <span class="val">184M</span>
      </div>
    </div>
  </div>

  <!-- Small graphs where the web was -->
  <div class="card mini-graphs">
    <div class="mini-graph-header">
      <h3>Network Activity</h3>
      <span class="pill">Past 10m</span>
    </div>
    <div class="sparkline-row">
      <div class="spark-card">
        <div class="spark-info">
          <b>Query Rate</b>
          <span>12.4 qps avg</span>
        </div>
        <canvas id="spark1" width="140" height="34"></canvas>
      </div>
      <div class="spark-card">
        <div class="spark-info">
          <b>Filter Efficacy</b>
          <span>99.8% clean</span>
        </div>
        <canvas id="spark2" width="140" height="34"></canvas>
      </div>
      <div class="spark-card">
        <div class="spark-info">
          <b>Latency</b>
          <span>14 ms to upstream</span>
        </div>
        <canvas id="spark3" width="140" height="34"></canvas>
      </div>
    </div>
  </div>
</div>

<!-- MIDDLE COLUMN: Board Vitals (Exact same spot) -->
<div class="col-mid">
  <div class="card board-card">
    <div class="card-title">
      <span>Board Performance</span>
      <span class="pill">UnoQ1</span>
    </div>
    
    <div class="vitals-meter">
      <div class="meter-label"><span>CPU Load</span><b>12%</b></div>
      <div class="meter-bar"><div class="meter-fill" style="width: 12%;"></div></div>
    </div>

    <div class="vitals-meter">
      <div class="meter-label"><span>Memory (RAM)</span><b>38.4 MB / 512 MB</b></div>
      <div class="meter-bar"><div class="meter-fill" style="width: 24%;"></div></div>
    </div>

    <div class="vitals-meter">
      <div class="meter-label"><span>Core Temperature</span><b>41.2 °C</b></div>
      <div class="meter-bar"><div class="meter-fill" style="width: 41%; background: #7BE2A8;"></div></div>
    </div>

    <div class="vitals-meter">
      <div class="meter-label"><span>System Uptime</span><b>2d 18h 42m</b></div>
    </div>
  </div>

  <div class="card lookup-card">
    <div class="card-title">
      <span>Live Lookups</span>
      <span class="pill" id="lookupBadge">Shielded</span>
    </div>

    <!-- Shown when LOCKED -->
    <div class="stealth-placeholder" id="lockedPlaceholder">
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
      <p>Live stream hidden behind password.</p>
      <button class="btn btn-sec" style="font-size:11px; padding:4px 10px;" id="unlockPromptBtn">Unlock Stream</button>
    </div>

    <!-- Shown when UNLOCKED -->
    <div class="lookup-stream" id="unlockedStream" style="display:none;">
      <div class="lookup-item"><span>apple.com</span><b style="color:#7BE2A8">PASS</b></div>
      <div class="lookup-item"><span>doubleclick.net</span><b style="color:#FF9A9A">DROP</b></div>
      <div class="lookup-item"><span>googlevideo.com</span><b style="color:#7BE2A8">PASS</b></div>
      <div class="lookup-item"><span>adservice.google.com</span><b style="color:#FF9A9A">DROP</b></div>
      <div class="lookup-item"><span>github.com</span><b style="color:#7BE2A8">PASS</b></div>
    </div>
  </div>
</div>

<!-- RIGHT COLUMN: Enlarged Network Topology Web -->
<div class="card col-right">
  <div class="web-stage">
    <div class="web-header">
      <h2>Device Network Topology</h2>
      <div class="pills">
        <span class="pill">Deacon 5G</span>
        <span class="pill">Gateway 100.69.33.51</span>
      </div>
    </div>
    <div class="web-canvas-container">
      <canvas id="webCanvas"></canvas>
    </div>
  </div>
</div>

<!-- Password Modal (Toggled via JS) -->
<div class="modal-overlay" id="passwordModal" style="display:none;">
  <div class="modal-card">
    <h3>Enter Master Passphrase</h3>
    <p>Unlock the active device livestream and detailed DNS inspection.</p>
    <input type="password" class="pass-input" placeholder="••••••••••••" value="admin123" id="passInput">
    <div class="modal-actions">
      <button class="btn btn-sec" id="cancelModalBtn">Cancel</button>
      <button class="btn btn-pri" id="submitModalBtn">Reveal Dashboard</button>
    </div>
  </div>
</div>

<script>
// Canvas Web Animation & Rendering
const canvas = document.getElementById('webCanvas');
const ctx = canvas.getContext('2d');

function resize() {
  canvas.width = canvas.parentElement.clientWidth * window.devicePixelRatio;
  canvas.height = canvas.parentElement.clientHeight * window.devicePixelRatio;
}
window.addEventListener('resize', resize);
resize();

const devices = [
  { label: 'MacBook Pro', ip: '203.0.113.254', rate: 4.2, color: '#7C67FE' },
  { label: 'iPhone', ip: '203.0.113.245', rate: 1.8, color: '#4ADE80' },
  { label: 'Arduino Uno Q', ip: '100.69.33.51', rate: 0.5, color: '#FBBF24' }
];

function drawSpark(id, data, color) {
  const c = document.getElementById(id);
  const x = c.getContext('2d');
  const w = c.width, h = c.height;
  x.clearRect(0,0,w,h);
  x.strokeStyle = color;
  x.lineWidth = 2;
  x.beginPath();
  data.forEach((v, i) => {
    const px = (i / (data.length - 1)) * w;
    const py = h - (v / 100) * h * 0.8 - 4;
    if (i === 0) x.moveTo(px, py); else x.lineTo(px, py);
  });
  x.stroke();
}
drawSpark('spark1', [20, 35, 25, 45, 60, 50, 75, 40, 65, 80], '#7C67FE');
drawSpark('spark2', [98, 99, 99, 100, 99, 100, 100, 99, 100, 100], '#7BE2A8');
drawSpark('spark3', [12, 14, 18, 15, 14, 13, 16, 14, 15, 14], '#FBBF24');

let frame = 0;
function drawWeb() {
  frame++;
  const W = canvas.width;
  const H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  const cx = W * 0.42;
  const cy = H * 0.5;

  // Draw Gateway Hub
  ctx.fillStyle = '#1E2330';
  ctx.strokeStyle = '#7C67FE';
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.arc(cx, cy, 28, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();

  ctx.fillStyle = '#fff';
  ctx.font = 'bold 12px sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('HUB', cx, cy);

  // Fanning devices
  devices.forEach((d, i) => {
    const angle = -Math.PI / 3 + (i * Math.PI / 3);
    const dist = Math.min(W, H) * 0.35;
    const dx = cx + Math.cos(angle) * dist;
    const dy = cy + Math.sin(angle) * dist;

    // Connecting line
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(dx, dy);
    ctx.stroke();

    // Pulse dot
    const pulseT = ((frame + i * 25) % 100) / 100;
    const px = cx + (dx - cx) * pulseT;
    const py = cy + (dy - cy) * pulseT;
    ctx.fillStyle = d.color;
    ctx.beginPath();
    ctx.arc(px, py, 4, 0, Math.PI * 2);
    ctx.fill();

    // Device node
    ctx.fillStyle = '#151922';
    ctx.strokeStyle = d.color;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(dx, dy, 24, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    // Device label
    ctx.fillStyle = '#E9EDF4';
    ctx.font = 'bold 13px sans-serif';
    ctx.fillText(d.label, dx, dy + 36);
    ctx.fillStyle = 'rgba(233, 237, 244, 0.5)';
    ctx.font = '11px sans-serif';
    ctx.fillText(d.ip, dx, dy + 52);
  });

  requestAnimationFrame(drawWeb);
}
drawWeb();

// State Switcher (Locked vs Unlocked)
let isUnlocked = false;
function applyState(unlocked) {
  isUnlocked = unlocked;
  const stage = document.getElementById('stageBanner');
  const heroTitle = document.getElementById('heroTitle');
  const heroSub = document.getElementById('heroSub');
  const lockStatus = document.getElementById('lockStatusText');
  const lockedPh = document.getElementById('lockedPlaceholder');
  const unlockedStream = document.getElementById('unlockedStream');
  const badge = document.getElementById('lookupBadge');

  if (unlocked) {
    stage.classList.add('unlocked');
    heroTitle.textContent = 'Streaming Video';
    heroSub.textContent = 'Active lookups: MacBook Pro watching YouTube • 4.2 qps';
    lockStatus.textContent = 'Unlocked';
    lockedPh.style.display = 'none';
    unlockedStream.style.display = 'flex';
    badge.textContent = 'Live Feed';
    badge.style.color = '#7BE2A8';
  } else {
    stage.classList.remove('unlocked');
    heroTitle.textContent = 'Quiet';
    heroSub.textContent = 'Network idle • All 3 devices shielded • Protection active';
    lockStatus.textContent = 'Locked';
    lockedPh.style.display = 'flex';
    unlockedStream.style.display = 'none';
    badge.textContent = 'Shielded';
    badge.style.color = '';
  }
}

// Modal handling
const modal = document.getElementById('passwordModal');
document.getElementById('lockToggleBtn').onclick = () => {
  if (isUnlocked) {
    applyState(false);
  } else {
    modal.style.display = 'flex';
  }
};
document.getElementById('unlockPromptBtn').onclick = () => { modal.style.display = 'flex'; };
document.getElementById('cancelModalBtn').onclick = () => { modal.style.display = 'none'; };
document.getElementById('submitModalBtn').onclick = () => {
  modal.style.display = 'none';
  applyState(true);
};
</script>
</body>
</html>
"""

with open(HTML_PATH, "w") as f:
    f.write(html_content)

print(f"Prototype written to {HTML_PATH}")

# Render Screenshots using Chrome Headless
def take_screenshot(url, out_path, click_selector=None):
    cmd = [
        CHROME_BIN,
        "--headless=new",
        "--user-data-dir=/tmp/chrome_preview_profile",
        "--no-sandbox",
        "--disable-gpu",
        f"--screenshot={out_path}",
        "--window-size=1440,900",
        url
    ]
    subprocess.run(cmd, check=True)
    print(f"Captured: {out_path}")

# 1. Screenshot Locked State
out_locked = os.path.join(ARTIFACT_DIR, "dashboard_stealth_locked.png")
take_screenshot(f"file://{HTML_PATH}", out_locked)

# 2. Modify state to Unlocked & take Screenshot
unlocked_html_path = os.path.join(SCRATCH_DIR, "stealth_dashboard_unlocked.html")
with open(HTML_PATH) as f:
    c = f.read()
# Pre-apply unlocked state
c_unlocked = c.replace("let isUnlocked = false;", "let isUnlocked = true;\nsetTimeout(() => applyState(true), 50);")
with open(unlocked_html_path, "w") as f:
    f.write(c_unlocked)

out_unlocked = os.path.join(ARTIFACT_DIR, "dashboard_stealth_unlocked.png")
take_screenshot(f"file://{unlocked_html_path}", out_unlocked)

# 3. Screenshot Modal State
modal_html_path = os.path.join(SCRATCH_DIR, "stealth_dashboard_modal.html")
c_modal = c.replace('style="display:none;" id="passwordModal"', 'style="display:flex;" id="passwordModal"')
with open(modal_html_path, "w") as f:
    f.write(c_modal)

out_modal = os.path.join(ARTIFACT_DIR, "dashboard_stealth_modal.png")
take_screenshot(f"file://{modal_html_path}", out_modal)

print("All preview screenshots generated successfully!")
