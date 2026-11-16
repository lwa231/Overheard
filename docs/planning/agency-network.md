# Network and placement — user decisions (2026-11-11 13:30 ET)
Status: decided by the user; nothing built. Open items at the bottom.

## Placement (hard)
- **Overheard lives on the Arduino UNO Q and always runs there.** Never moved.
- **The agency (code, files, instructions, handoffs, ledger) lives only on the local Ubuntu server.** Nothing of the agency is stored on the VPS, the Arduino or the Mac.
- **Mac**: SSH into the local server only. No agency code on the Mac.
- **Hostinger VPS**: Telegram bot node. It sends and receives Telegram messages for the agency and relays them; it holds no agency code.
- Overheard and the agency talk through a small **API** between the Arduino and the server.

## Access model (user's words, to be enforced by rules, not trust)
- The Arduino acts as the **security and confidentiality manager** for the network (DNS filtering, firewall rules, who may talk to whom).
- The VPS and the local server each get read-write access to the Arduino's API. Use a separate token per client.
- Intent: all traffic from the Mac, the phone and the Ubuntu server is filtered through Overheard, so agents do not run on a plain public network.

## Design notes (from Claude, for review)
- DNS filtering is not a firewall. Real containment = default-deny outbound firewall on the server (allow only the Claude API, Telegram, Tailscale, package mirrors) + Tailscale ACLs + the DNS filter.
- Enforce "who can reach what" with **Tailscale ACLs** (tags: `tag:board`, `tag:server`, `tag:vps`, `tag:mac`), not by relaying control traffic through the Arduino. A relay makes the small board a single point of failure and a high-value target.
- Telegram: only the user's Telegram ID is accepted; messages are instructions to the boss agent, not shell. Spend/purchase approvals over Telegram need a confirmation code (guardrails in playbook section 7 still apply).
- Server DNS = the board, with a fallback resolver so a board outage does not freeze the agents.
- Overheard's locked `/api/stats` carries no domains; the agency API must keep that rule. Agents get aggregates only unless the user unlocks.

## What Tailscale is
A private network between the user's own devices (WireGuard underneath). Each device runs the Tailscale app, logs into the same account, and gets a stable `100.x` address and name. Devices reach each other from anywhere with no open router ports. The control service is Tailscale's (third party); traffic goes device-to-device, encrypted. It runs on each device (the board, the Mac, the server, the VPS), not as a server on the Arduino. The admin console sets DNS, ACLs and exit nodes.

## Gate (planned, after the agency is set up — user decision 13:43 ET)
Separate program that controls an nftables firewall and takes cues from Overheard (e.g. allow a device to connect only to addresses its DNS recently resolved). The board may act as a Tailscale exit node; the VPS is the alternative exit node (no Wi-Fi bottleneck, filtering then sits on the VPS). Order: agency server egress first (default-deny), then the Mac, test board throughput before the phone. Needs a fail-open or fail-closed choice (board down = no internet for routed devices). Unverified on UNO Q hardware. Status as of 13:43: Tailscale installed on phone and Mac (GitHub login); server, VPS, board not yet; Mac DNS command given, result unknown.

## Findings (2026-11-11 evening)
- Server: Ubuntu Server 26.04.1 installed, user `awl`, host `awlserver`, wired on `eno1` (internet works). Root disk is LUKS2-encrypted (`/dev/sdc3`, passphrase at boot); TPM 2.0 present, dracut initramfs, Secure Boot off. TPM auto-unlock enrolled (PCR 7) and one unattended reboot confirmed over SSH; passphrase and recovery key remain as fallbacks (a BIOS update or Secure Boot change will force the passphrase at the console). Server DNS = the board over the tailnet, user-confirmed.
- The server's Ethernet and the board's Wi-Fi (`100.69.41.76`) are separate networks: ping and DNS from the server to the board time out. The board is not on Tailscale (`100.69.x` is the building Wi-Fi range). Server ↔ board needs Tailscale on both (or another routed path), plus the server's address on Overheard's allow-list.
- Server keeps the building's DNS until that link exists.
- Later the same evening: Tailscale is on the board, server, Mac and iPhone (one tailnet; addresses in `last-tailscale.txt`, kept out of the repo). Overheard answers the server over the tailnet (`doubleclick.net` → 0.0.0.0). Mac → server key login works. Agency repo deployed: bare repo `~/agency.git` and checkout `~/agency` on the server (Mac git remote `server`), smoke test passes on Python 3.14. Not done: server DNS switched to the board, pytest/ruff on the server, post-commit hook to the Arduino log, GitHub mirror job, SSH password login off.

## Open
1. Is Tailscale installed on the board? `Check Overheard.command` now prints `tailscale status` into `last-check.txt`.
2. Mac, phone, server and VPS into one tailnet; global nameserver = the board's tailnet IP.
3. ACL policy and per-client API tokens; the Arduino↔server API shape.
4. Telegram bot design (VPS), Mac→server SSH hardening (keys only).
