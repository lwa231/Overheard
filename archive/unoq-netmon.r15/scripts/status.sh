#!/usr/bin/env bash
# Tells you whether the board is running Overheard and whether DNS answers. Run from the Mac:  bash scripts/status.sh
BOARD="${BOARD:-}"
if [ -z "$BOARD" ]; then
  if nc -z -G 3 100.69.33.51 22 >/dev/null 2>&1; then BOARD="arduino@100.69.33.51"
  elif ping -c1 -t3 UnoQ1.local >/dev/null 2>&1; then BOARD="arduino@UnoQ1.local"
  else echo "Cannot find the board on this network. Is it powered and on the same Wi-Fi? You can also run: BOARD=arduino@<its address> bash $0"; exit 1; fi
fi
HOST="${BOARD#*@}"
REAL="$(ssh -o ConnectTimeout=8 "$BOARD" "hostname -I" 2>/dev/null | awk '{print $1}')"; case "$HOST" in *.local) [ -n "$REAL" ] && HOST="$REAL" ;; esac
echo "Board reached as: $HOST"
ssh -o ConnectTimeout=8 "$BOARD" 'echo "The board'"'"'s real address(es), use one of these as the DNS server:"; hostname -I; systemctl is-active overheard.service 2>/dev/null || echo "service not installed (run: bash scripts/install.sh)"' || echo "Cannot reach the board over SSH."
printf "Dashboard: "; curl -fsS -m 4 "http://$HOST:8080/api/health" >/dev/null 2>&1 && echo up || echo "NOT answering"
ok_ip() { grep -qE '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; }      # a real answer is an address; dig prints timeouts on stdout too
A="$(dig +short +time=3 +tries=1 @"$HOST" example.com 2>&1 | head -1)"
B="$(dig +short +time=3 +tries=1 @"$HOST" doubleclick.net 2>&1 | head -1)"
printf "DNS answers (example.com): "; echo "$A" | ok_ip && echo "yes ($A)" || { echo "NO"; FAIL=1; }
printf "Ad domain blocked (doubleclick.net, expect 0.0.0.0): "; echo "$B" | ok_ip && echo "$B" || { echo "NO ANSWER"; FAIL=1; }
if [ -n "${FAIL:-}" ]; then
  echo
  echo "--- DNS is not answering. Details from the board (send these lines to Claude) ---"
  ssh -o ConnectTimeout=8 "$BOARD" 'echo "[port 53 listeners]"; ss -lun | grep ":53 " || echo "nothing listening on UDP 53"; echo "[service log]"; (sudo -n journalctl -u overheard -n 15 --no-pager 2>/dev/null || journalctl -u overheard -n 15 --no-pager 2>&1) | tail -15; echo "[board asking itself]"; python3 - <<PY
import socket,struct
q=struct.pack("!HHHHHH",7,0x0100,1,0,0,0)+b"\\x07example\\x03com\\x00"+struct.pack("!HH",1,1)
for ip in ("127.0.0.1","'$HOST'"):
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(3)
    try:
        s.sendto(q,(ip,53));print(ip,"answers",len(s.recvfrom(512)[0]),"bytes")
    except Exception as e: print(ip,"no answer:",e)
PY
echo "[firewall]"; (sudo -n iptables -S 2>/dev/null | head -8) || true' 2>&1
fi
