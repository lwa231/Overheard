#!/bin/bash
# Double-click on the Mac: install or update the agency dashboard on the server.
# The server's SSH address is read from the git remote named "server", so no address is stored in this repo.
set -uo pipefail
cd "$(dirname "$0")" || exit 1

fail() { echo; echo "FAILED: $*"; read -r -p "Press Return to close. "; exit 1; }

url="$(git remote get-url server 2>/dev/null)" || fail "there is no git remote named server (git remote add server <user>@<host>:agency.git)"
target="${url%%:*}"
case "$url" in *://*) fail "the server remote must look like user@host:path (not a URL)" ;; esac
[ "$target" != "$url" ] || fail "the server remote must look like user@host:path"

echo "== Smoke test (local)"
python3 scripts/smoke.py || fail "the smoke test failed; nothing was pushed"
echo "== Push to the server"
git push server main || fail "git push server main failed"
echo "== Install on the server (it may ask for the server password for sudo)"
rc=0
ssh -t "$target" 'cd ~/agency && git pull -q origin main && bash scripts/install.sh' || rc=$?
scp -q "$target:agency-install.txt" "$HOME/Desktop/ArduinoQ/last-agency-install.txt" || echo "(could not copy the summary back)"
echo
if [ "$rc" -eq 0 ]; then echo "Done. Summary: ~/Desktop/ArduinoQ/last-agency-install.txt"; else echo "The install reported a problem (exit $rc). See ~/Desktop/ArduinoQ/last-agency-install.txt"; fi
read -r -p "Press Return to close. "
