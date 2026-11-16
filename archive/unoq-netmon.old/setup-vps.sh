#!/usr/bin/env bash
# One-time VPS setup, run from your Mac:  ./setup-vps.sh
# 1) installs your SSH key on the VPS (you type the VPS root password ONCE)
# 2) installs Tailscale and turns the VPS into an exit node (a VPN location)
# Nothing here changes the VPS firewall, SSH settings or opens any public port.
set -euo pipefail
VPS=${VPS:-root@198.51.100.10}
KEY="$HOME/.ssh/id_ed25519"
[ -f "$KEY" ] || ssh-keygen -t ed25519 -N "" -f "$KEY"
echo "Installing your key on $VPS. Type the VPS root password when asked (once)."
ssh-copy-id -i "$KEY.pub" "$VPS"
echo "Setting up Tailscale on the VPS..."
ssh -o BatchMode=yes "$VPS" 'bash -s' <<'REMOTE'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
command -v tailscale >/dev/null 2>&1 || curl -fsSL https://tailscale.com/install.sh | sh
cat >/etc/sysctl.d/99-tailscale.conf <<'EOF'
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
EOF
sysctl -p /etc/sysctl.d/99-tailscale.conf
systemctl enable --now tailscaled
echo
echo ">>> Open the login link below in your browser and sign in to Tailscale <<<"
tailscale up --advertise-exit-node --hostname=vps-exit
echo
tailscale status | head -5
REMOTE
cat <<'EOT'

Done on the server. Last step, in your browser (about 1 minute):
  1. Open https://login.tailscale.com/admin/machines
  2. Find "vps-exit", click the three dots, then "Edit route settings"
  3. Tick "Use as exit node" and save
Then on your phone: Tailscale app, Exit node, vps-exit.
EOT
