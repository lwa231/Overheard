#!/usr/bin/env bash
# Install (or update) the agency dashboard as a systemd service on THIS machine.
# Run on the server as the normal user, from the repo checkout:  bash scripts/install.sh
# Safe to run again. sudo is used only for the systemd unit; it asks through the normal sudo prompt.
# Env: AGENCY_PORT (default 8088), AGENCY_DATA_DIR (default <repo>/data).
set -euo pipefail

NAME=agency-dashboard
PORT="${AGENCY_PORT:-8088}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="${AGENCY_DATA_DIR:-$REPO/data}"
OUT="$HOME/agency-install.txt"
UNIT="/etc/systemd/system/$NAME.service"

: > "$OUT"
die() { printf 'agency install: %s\n' "$*" | tee -a "$OUT" >&2; exit 1; }
say() { printf '%s\n' "$*" | tee -a "$OUT"; }
answers() { python3 -c 'import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=2).read()' "$1" >/dev/null 2>&1; }

[ "$(id -u)" -ne 0 ] || die "run as your normal user, not root (sudo is asked for when needed)"
case "$PORT" in ''|*[!0-9]*) die "AGENCY_PORT must be a number" ;; esac
[ "$PORT" -ge 1024 ] && [ "$PORT" -le 65535 ] || die "AGENCY_PORT must be from 1024 to 65535"
case "$REPO$DATA" in *[[:space:]]*) die "the repo and data paths must not contain spaces" ;; esac
command -v python3 >/dev/null || die "python3 is not installed"
command -v tailscale >/dev/null || die "tailscale is not installed"
command -v systemctl >/dev/null || die "systemd is required"

TS_IP="$(tailscale ip -4 2>/dev/null | head -n 1 || true)"
case "$TS_IP" in
  [0-9]*.[0-9]*.[0-9]*.[0-9]*) ;;
  *) die "Tailscale is not up (no IPv4 address). Run: sudo tailscale up   then run this again" ;;
esac

mkdir -p "$DATA"
chmod 700 "$DATA"
# the access key: created with the project's own code if missing, never printed (mode 600)
PYTHONPATH="$REPO/src" python3 -c 'import sys; from agency import auth; auth.load_token(sys.argv[1])' "$DATA"

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
cat > "$TMP" <<UNITFILE
[Unit]
Description=Agency dashboard (Tailscale only)
After=network-online.target tailscaled.service
Wants=network-online.target tailscaled.service
StartLimitIntervalSec=0

[Service]
Type=simple
User=$(id -un)
WorkingDirectory=$REPO
Environment=PYTHONPATH=$REPO/src
ExecStart=$(command -v python3) -m agency --root $REPO --data-dir $DATA --host $TS_IP --port $PORT
Restart=on-failure
RestartSec=5
StandardOutput=null

[Install]
WantedBy=multi-user.target
UNITFILE

sudo install -m 644 "$TMP" "$UNIT"
sudo systemctl daemon-reload
sudo systemctl enable "$NAME" >/dev/null
sudo systemctl restart "$NAME"

URL="http://$TS_IP:$PORT/"
up=no
for _ in $(seq 1 30); do
  if answers "${URL}api/health"; then up=yes; break; fi
  sleep 1
done

say "Agency install, $(date '+%Y-%m-%d %H:%M')"
say "Service:   $NAME ($(systemctl is-active "$NAME" 2>/dev/null || true), starts on boot)"
say "Address:   $URL  (reachable over Tailscale only)"
if [ "$up" = yes ]; then say "Health:    answering"; else say "Health:    NOT answering after 30 s. Look: journalctl -u $NAME -n 50 --no-pager"; fi
say "Key file:  $DATA/token  (open the dashboard once as ${URL}?key=<the file's contents>)"
if answers "http://127.0.0.1:11434/api/tags"; then say "Ollama:    answers on 127.0.0.1:11434"; else say "Ollama:    does not answer on 127.0.0.1:11434 (only needed for test mode)"; fi
say "Summary saved to $OUT"
[ "$up" = yes ]
