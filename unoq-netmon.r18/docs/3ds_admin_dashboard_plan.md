# New Nintendo 3DS XL Administrator Dashboard Plan
**Hardware Target:** New Nintendo 3DS XL (2015 "New" Variant, RED-001, Luma3DS CFW / Homebrew Enabled)  
**Host System:** Arduino Uno Q (Overheard Netmon / DNS Engine) + Cloudflare / Hostinger VPS

---

## 1. Hardware & Platform Profile

The 2015 **New Nintendo 3DS XL** is an exceptionally capable micro-console for a dedicated home-lab/network operations monitor:

* **Processing Power:** Quad-core ARM11 MPCore @ 804 MHz (3x the speed of the original 2011 3DS) with 256 MB FCRAM.
* **Dual Display Architecture:**
  * **Top Screen (400 × 240 px, 24-bit color):** Ideal for persistent telemetry, status banners (*Quiet* / *Active*), live CPU/RAM meters, and the device network web.
  * **Bottom Screen (320 × 240 px with Resistive Touch):** Ideal for the administrator touch interface: PIN keypad, device toggles, blocklist status, and DNS switches.
* **Wi-Fi Connectivity:** Built-in 802.11b/g (2.4 GHz only). Supports standard WPA2-PSK (AES).
  > Note: The 3DS hardware only detects **2.4 GHz Wi-Fi** networks. Ensure your router/AP broadcasts a 2.4 GHz SSID.

---

## 2. Network Integration & DNS Routing

### DNS Identification in Overheard
In `src/overheard/fingerprint.py`, Overheard already contains the fingerprint rule for Nintendo hardware:
```python
("Nintendo console", "nintendo", 3, ("nintendo.net", "nintendo.com")),
```
When the 3DS connects to Wi-Fi and queries Nintendo's connectivity servers (`conntest.nintendowifi.net`, `ecs.nintendo.net`), Overheard automatically tags its IP as **`Nintendo console`** on the network map.

---

## 3. Two Development Paths

### Path A: Dedicated Dual-Screen Web Dashboard (Fastest, Zero Compile)
The New 3DS XL features an updated NetFront NX WebKit browser engine with HTML5 Canvas, CSS3, and DOM touch events.

* **How it works:**
  Overheard serves a dedicated endpoint `/3ds` formatted specifically for the 3DS's dual-screen viewport (400px top, 320px bottom).
* **Top Viewport (400x240):**
  * Live status headline (`Quiet.` / streaming detection).
  * UnoQ1 core temperature, RAM, and CPU gauge.
  * Vector-scaled network topology web.
* **Bottom Viewport (320x240):**
  * Touch keypad for developer PIN entry.
  * Toggles for DNS protection, ad-filter bypass, and device isolation.
* **Access:** Open the 3DS Internet Browser, bookmark `http://<board-ip>:8080/3ds?key=<token>` (or your Cloudflare Tunnel URL).

---

## 4. Path B: Native Homebrew CIA App (Standalone Console Experience)
A standalone `.cia` app installed directly to the 3DS Home Menu with a custom Overheard icon and 3D banner.

#### Toolchain Options on PC:
1. **Option 1: LovePotion (LÖVE 2D for 3DS) — Recommended for Quick UI:**
   * Scripted in pure **Lua 5.1**.
   * Provides native dual-screen drawing: `love.graphics.setScreen('top')` and `love.graphics.setScreen('bottom')`.
   * Native touch input: `love.touchpressed(id, x, y)`.
   * HTTP requests via LuaSocket or libcurl to poll `/api/stats`.
   * Builds into a `.3dsx` (run via Homebrew Launcher) or `.cia` (install via FBI) in seconds.

2. **Option 2: devkitPro (devkitARM + libctru + Citro2D):**
   * Standard C/C++ toolchain for 3DS.
   * Direct hardware access via `citro2d` for 60 FPS GPU-accelerated rendering.
   * `httpc` service in CTR-OS for native network transfers.

---

## 5. Cloudflare Integration Architecture

If accessing the dashboard remotely (away from the home Wi-Fi):
1. **Cloudflare Tunnel (`cloudflared`):**
   * Runs as a lightweight service on your Hostinger VPS or board.
   * Routes `https://netmon.yourdomain.com` securely to `http://localhost:8080` without opening incoming firewall ports.
2. **Cloudflare Access (Zero Trust):**
   * Protects the 3DS endpoint with service tokens or HTTP Basic Auth compatible with the 3DS browser/HTTP stack.

---

## 6. Phased Implementation Roadmap

* **Step 1:** Build `src/overheard/web/3ds.html` tuned precisely to 400x240 (top) and 320x240 (bottom) with touch controls and PIN lock.
* **Step 2:** Test directly on your New 3DS XL browser using your local IP.
* **Step 3:** Setup Cloudflare Tunnel for secure remote routing.
* **Step 4:** Package the standalone LovePotion / CIA app for the 3DS Home Menu.
