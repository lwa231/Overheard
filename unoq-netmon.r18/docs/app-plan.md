# Custom app plan

## Can the dashboard live inside the app?
Yes. The dashboard is a plain web page served by the board, so the app only needs a window that loads it.

- Shell: a thin native wrapper (Tauri or a Swift WKWebView) around `http://<board>:8080`. No dashboard code is duplicated; the board stays the single source of truth.
- Access key: stored in the macOS Keychain, sent as the `ov` cookie on first load. The user never sees or pastes the `?key=` URL.
- Transport: move the dashboard behind Tailscale (WireGuard) with HTTPS from `tailscale serve`, so the app talks to the board over an encrypted tunnel even on the building Wi-Fi.
- Installer: `.dmg` for drag-to-Applications, or a `.pkg` for the standard installer prompts. Signing and notarization need an Apple Developer account (99 USD/yr); without it users get a Gatekeeper warning.
- Extras the app can add over a browser tab: menu-bar status icon, native notifications (device slowed, new flagged site), auto-start at login, board auto-discovery.

## Filters are not user-controllable
The adult guard, its slowdown, and DNS SafeSearch have no flag, no setting, no API route and no UI control. Strength values are constants in code, and the allowlist file is gone. Tests assert the old flags are rejected.

Honest limit: anyone who can SSH into the board or edit the source can change the code. Making that true even for the owner needs a locked-down deployment: root-owned read-only install, a systemd service with no write access to it, a signed release the board verifies at start, and no password SSH. That is a deployment decision for later.

## Traffic decryption (later, own devices only)
- mitmproxy on the board in transparent or explicit-proxy mode, enabled per device after an explicit consent prompt in the app.
- A local CA installed on each consenting device; CA private key kept on the board, mode 600, never exported.
- Bypass list for banking, health, password managers and anything certificate-pinned. Pinned apps will fail by design and must be bypassed.
- Store only derived metadata (host, path category, size, timing), never bodies or credentials.
- One-tap kill switch in the app that stops the proxy and removes the redirect.
- Decrypting only your own devices with their consent is legal and ordinary; decrypting anyone else's is not.
