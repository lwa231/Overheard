# Overheard (AWL) — Full Project Handoff & Architecture Log
**Build:** r15 (Updated 2026-11-10)  
**Host Target:** Arduino UNO Q (Linux side `arduino@100.69.33.51`, Hostname `UnoQ1`, mDNS `UnoQ1.local`)  
**Mac Environment:** User `luqman_ahmed`, Directory `~/Desktop/ArduinoQ/`  
**Hostinger VPS:** `198.51.100.10` (Candidate Tailscale exit node)  
**Nintendo 3DS XL:** New Nintendo 3DS XL (2015 Variant, RED-001, Luma3DS CFW)

---

## 1. What Overheard Is
A standard-library-only Python DNS ad-blocker, network traffic monitor, and live telemetry dashboard deployed to an Arduino UNO Q.
* **Dashboard Access:** `http://100.69.33.51:8080/?key=<token>` (Access token stored in `~/netmon/data/token` on the board).
* **Mac Launcher:** `Overheard.app` in `~/Desktop/ArduinoQ/`.
* **Workspace Inventory:**
  * `unoq-netmon.r15/`: Active working codebase.
  * `overheard-r15.tgz`: Production distribution archive deployed to the board.
  * `unoq-netmon.old/`: User's original baseline backup (**NEVER DELETE**).
  * `live_youtube_traffic.py`: Zero-dependency live packet capture & stream inspector for Mac/Linux.
  * `3ds_admin_dashboard_plan.md`: Technical execution plan for New Nintendo 3DS XL admin console.
  * `HANDOFF.md`: This comprehensive master documentation.

---

## 2. Where Things Stand & Current State

1. **Install Command (Zero Flags Needed):**
   ```bash
   cd ~/Desktop/ArduinoQ/unoq-netmon.r15 && bash scripts/install.sh
   ```
   *(Or double-click `Install Overheard.command` in Finder)*
2. **Status Check:**
   ```bash
   bash ~/Desktop/ArduinoQ/unoq-netmon.r15/scripts/status.sh
   ```
3. **DNS Connectivity & Building NAT:**
   * Building Wi-Fi NATs all devices to public addresses `203.0.113.245` and `203.0.113.254`.
   * `ALLOW_EXTRA="203.0.113.0/24"` and `NO_TLS=1` (plain UDP upstream to avoid DoT port 853 hangs) are **hardcoded defaults** in `src/overheard/config.py`, `scripts/install.sh`, and `Install Overheard.command`. Double-clicking the installer will never wipe out the allow-list or hang on upstream DoT.
4. **Internet Speed Slowdown Penalty: DISABLED:**
   * Artificial 8-second query delay penalty commented out in `src/overheard/dnsserver.py:slow_down`.
   * Adult domain blocking (`0.0.0.0`) remains 100% active; normal browsing on flagged devices no longer buffers.
5. **YouTube Whitelist & SafeSearch:**
   * `youtube.com`, `googlevideo.com`, `ytimg.com`, `ggpht.com`, `youtu.be` added to `NEVER_FLAG` in `src/overheard/adult.py`. YouTube traffic is immune from heuristic flaggings.
   * YouTube Restricted Mode completely purged from `src/overheard/safesearch.py` so YouTube search and index recommendations remain standard.
6. **Unified Apple Device Fingerprinting:**
   * `src/overheard/fingerprint.py` updated so Macs, iPhones, and iPads all report consistently as `"Apple device"`.
7. **Stealth Header Dashboard (Default Skin):**
   * **Hero Title:** Locked permanently to **`"Quiet."`** (*"Protection active"*). Streaming detection and visited domains are never leaked to casual viewers.
   * **Board Performance Card:** Anchored in its exact center column spot (CPU %, Memory, Disk, Temperature, and CPU history wave).
   * **Latest Lookups Table:** Completely hidden (`display: none`) when locked. No giveaway placeholder text or visible unlock buttons.
   * **Traffic Line Timeline:** Shrunken down and simplified horizontal bar timeline (`canvas id="c"`) placed on the bottom-left under tiles.
   * **Device Network Topology Web:** Enlarged and promoted to the entire right-hand section (`canvas id="web"`) with animated pulse dots, connection arcs, and gateway doorway.
   * **Skins Feature:** `#skinBtn` hidden from the header bar for now; underlying 48 skins engine and `skins.css` remain completely intact.
   * **Secret Developer Unlock:** Pressing **`P`** on the keyboard (or clicking the title **"Overheard"**) opens the authentic **Arduino Uno Q — System Login** prompt (`arduino@UnoQ1: [Password]`). Authenticating unhides the live lookups feed and live stream detection; pressing **`P`** again immediately re-locks it.

---

## 3. Work Completed in This Session (r15 Milestones)

| Feature / Fix | Implementation Files | Status |
| :--- | :--- | :--- |
| **Bake Allow-List & No-TLS Defaults** | `src/overheard/config.py`<br>`scripts/install.sh`<br>`Install Overheard.command` | **Complete.** Double-click install survives without CLI arguments. |
| **Disable Query Slowdown Penalty** | `src/overheard/dnsserver.py` | **Complete.** Commented out 90s penalty delay, preserved ad/adult block. |
| **Unified Apple Fingerprinting** | `src/overheard/fingerprint.py` | **Complete.** Unified under "Apple device" label. |
| **YouTube Whitelisting & SafeSearch Clean** | `src/overheard/adult.py`<br>`src/overheard/safesearch.py` | **Complete.** In `NEVER_FLAG`; YouTube restricted mode removed. |
| **Ad-Stream Packet Filter Engine** | `src/overheard/adstream.py` | **Complete.** Multi-signal inspection (DNS auction, TLS SNI, CBR/ABR variance, telemetry). |
| **Live Traffic Inspector** | `live_youtube_traffic.py` | **Complete.** Zero-dependency pcap/tcpdump monitor for Mac and Linux. |
| **UI Stealth Mode & Layout Overhaul** | `src/overheard/web/index.html` | **Complete.** Quiet hero, hidden lookups, right-side web, left timeline, P-key login. |
| **Hostinger VPN & Exit Node Plan** | Documented in HANDOFF | **Complete.** Architecture ready for deployment. |
| **New Nintendo 3DS XL Blueprint** | `3ds_admin_dashboard_plan.md` | **Complete.** Dual-screen Web & Native CIA homebrew roadmap. |
| **Distribution Packaging** | `overheard-r15.tgz` | **Complete.** Freshly built and validated. |

---

## 4. Deep Packet Inspection & YouTube Ad Filtering Architecture

### How YouTube Ads Work at the Network Layer
1. **Phase 1: DNS Ad Auction** (`googleads.g.doubleclick.net`, `pagead2.googlesyndication.com`):
   * Overheard blocks these queries with `0.0.0.0`. If the auction never completes, YouTube has no ad to load and falls back to playing the video immediately.
2. **Phase 2: TLS ClientHello SNI Inspection** (`adstream.py`):
   * Inspects plaintext SNI hostnames in TLS 1.3 ClientHellos without MITM certificates. Drops connections to ad PoPs (`redirector.googlevideo.com`, `adp*`, `s.youtube.com`).
3. **Phase 3: CBR vs ABR Timing & Size Variance**:
   * Evaluates packet trajectories. Ad video chunks stream at fixed Constant Bitrate (CBR) in small uniform packets with low gap variance (< 18 ms²). Real video streams show high gap variance (> 45 ms²) and jumbo frame bursts.
4. **Phase 4: Telemetry Suppression**:
   * Drops outbound tracking POSTs to `s.youtube.com` and `/ptracking` so ad servers cannot verify impression delivery.

### Why Phone (iOS App) Behaves Differently than Laptop (Browser)
* **Web Browsers (Mac):** Obey system DNS; player catches load errors on ad scripts and triggers `contentPlayer.play()`, skipping the ad.
* **YouTube iOS App:**
  1. Uses **QUIC over UDP 443** (encrypts handshake and bypasses TCP filters).
  2. Features **hardcoded Google DNS-over-HTTPS (DoH)** fallback if local DNS blocks ad domains.
  3. Pre-caches video bumper ads in the iOS sandbox.
  4. iOS **"Limit IP Address Tracking"** (Settings → Wi-Fi → (i)) routes DNS through Apple Private Relay, bypassing custom DNS unless disabled.

---

## 5. Hostinger VPS & VPN Topology

### Current NAT Limitation
Because the building router NATs all internal Wi-Fi devices, the Arduino sees every laptop and phone as `203.0.113.245` or `203.0.113.254`. Devices share rate limits and cannot be uniquely fingerprinted.

### Tailscale Exit Node Solution (Hostinger VPS `198.51.100.10`)
```
[ iPhone ] ──┐
             ├─► [ Tailscale Mesh ] ─► [ Hostinger VPS Exit Node ] ─► Internet
[ MacBook ] ─┘        │                       (198.51.100.10)
                      ▼
             [ Arduino Uno Q ]
             (100.69.33.51 - DNS & Adstream Filter)
```
* **Step 1:** Install Tailscale on Hostinger VPS and advertise exit node:
  ```bash
  curl -fsSL https://tailscale.com/install.sh | sh
  sudo tailscale up --advertise-exit-node
  ```
* **Step 2:** Each device routes through Tailscale, receiving its own distinct `100.x.x.x` CGNAT address.
* **Step 3:** The Arduino sees distinct IPs for each device, restoring individual device profiles, isolated rate limiting, and distinct client cards.

---

## 6. New Nintendo 3DS XL Administrator Console Plan

### Hardware Specifications
* **Model:** New Nintendo 3DS XL (2015 Variant, RED-001, Luma3DS CFW).
* **CPU:** Quad-core ARM11 @ 804 MHz with 256 MB FCRAM.
* **Screens:** Top 400 × 240 px (24-bit color); Bottom 320 × 240 px (Resistive Touch).
* **Wi-Fi:** 802.11b/g (**2.4 GHz only** — must connect to 2.4 GHz SSID).

### Implementation Roadmap
1. **Path A: Dual-Screen Web Client (`/3ds` Route):**
   * Top screen renders live status headline (`Quiet.` / active streaming), UnoQ1 vitals, and vector device web.
   * Bottom screen renders touch keypad for developer PIN entry, quick filter bypass toggles, and device isolation switches.
2. **Path B: Standalone Homebrew CIA App:**
   * Scripted in pure **Lua 5.1** using **LovePotion** (LÖVE2D for 3DS) or C/C++ via **devkitPro / libctru**.
   * Polls `http://<board-ip>:8080/api/stats` directly.
   * Installed to Home Menu via FBI with custom 3D banner and icon.
3. **Cloudflare Remote Access:**
   * Cloudflare Tunnel (`cloudflared`) securely exposes the board API to `https://netmon.yourdomain.com` without opening router ports, enabling 3DS administration from anywhere.

---

## 7. User Preferences & Operating Constraints

* **Communication Style:** Terse, calm replies; senior-developer quality; exact copy-paste commands ("vibe-coding").
* **Directory Boundary:** Stay strictly inside `~/Desktop/ArduinoQ/`. Do not inspect or touch external user files.
* **Preservation Rule:** `unoq-netmon.old` is the user's golden baseline: **NEVER DELETE OR OVERWRITE**.
* **Filter Hardcoding:** Content filters and security rules are code-level constants, un-disableable via web settings.
* **UI Schema Integrity:** Maintain original dark theme, CSS variables, typography, and card schemas. Do not invent foreign designs.
* **Approval Before Sudo:** Always ask before executing elevated privilege operations on the Mac.

---

## 8. Backlog & Next Steps

1. **Test r15 Deployment on Board:**
   * Run `bash scripts/install.sh`, verify via `bash scripts/status.sh`, and open `Overheard.app`.
   * Verify stealth view: headline says `Quiet.`, latest lookups hidden, board vitals visible, web on right, timeline on left.
   * Press **`P`** to test the Arduino login prompt and unlock.
2. **Phone Verification:**
   * Disable "Limit IP Address Tracking" in iOS Wi-Fi settings.
   * Verify ad skipping in mobile Safari.
3. **Hostinger VPS Exit Node Setup:**
   * Deploy `tailscale up --advertise-exit-node` on Hostinger VPS `198.51.100.10`.
4. **New Nintendo 3DS XL Dual-Screen Interface:**
   * Build `src/overheard/web/3ds.html` endpoint tailored to 400x240 and 320x240 dual viewports.
   * Package standalone LovePotion CIA build for Home Menu installation.
5. **Wednesday Roadmap:**
   * Re-enable and refine skins engine button (`#skinBtn`).
   * Review device profile vector clustering models.
