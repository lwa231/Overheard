#!/usr/bin/env bash
# Links the boards so each dashboard can show the others (a read-only, locked summary).
# For every sites/<name>.conf (not the *.example templates): reads that board's access key over SSH, then writes
# ~/netmon/data/peers.json (mode 600) on every board listing all the OTHER boards, and restarts the service.
# Reading is all or nothing: if any board cannot be read, nothing is written to any board.
# Writing is NOT atomic (separate SSH sessions): if a write fails part-way, it stops, exits non-zero and last-link-sites.txt says
# exactly which boards were written ("ok") and which were not ("not written"); the boards that say ok keep their new list.
# Keys are only ever held in this script's memory: never printed, never written on this Mac.
# Needs two or more sites, each with BOARD_HOST set to the board's Tailscale address (100.64.0.0 to 100.127.255.255).
# Run from the project folder:  bash scripts/link_sites.sh
cd "$(dirname "$0")/.." || exit 1
OUTDIR="$HOME/Desktop/ArduinoQ"; OUT="$OUTDIR/last-link-sites.txt"
NAMES=(); USERS=(); HOSTS=(); KEYS=(); RES=()
for f in sites/*.conf; do [ -f "$f" ] && NAMES+=("$(basename "$f" .conf)"); done
if [ "${#NAMES[@]}" -lt 2 ]; then
  echo "Linking needs at least two sites: one file per board in sites/ (sites/home.conf and sites/apartment.conf)."
  echo "Copy sites/home.conf.example to sites/home.conf, fill in that board's Tailscale address, then run this again."
  exit 0
fi
O="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"
# a real dotted IPv4 inside 100.64.0.0/10, no leading zeros
OCT='(0|[1-9][0-9]{0,2})'; IPRE="^$OCT\\.$OCT\\.$OCT\\.$OCT\$"
tsip() { [[ "$1" =~ $IPRE ]] && [ "${BASH_REMATCH[1]}" -eq 100 ] && [ "${BASH_REMATCH[2]}" -ge 64 ] && [ "${BASH_REMATCH[2]}" -le 127 ] \
  && [ "${BASH_REMATCH[3]}" -le 255 ] && [ "${BASH_REMATCH[4]}" -le 255 ]; }
# 1. who and where, then each board's access key (read into memory only)
for i in "${!NAMES[@]}"; do
  n="${NAMES[$i]}"; RES[$i]="ok"
  case "$n" in ""|*[!a-z0-9-]*) RES[$i]="skipped (site names are a-z, 0-9 and - only)"; continue;; esac
  [ "${#n}" -le 24 ] || { RES[$i]="skipped (site name longer than 24)"; continue; }
  line="$( (unset BOARD_USER BOARD_HOST BOARD_MDNS; SITE="$n"; . scripts/board.sh >/dev/null 2>&1 && echo "$BOARD_USER $BOARD_HOST") )"
  USERS[$i]="${line%% *}"; HOSTS[$i]="${line#* }"
  tsip "${HOSTS[$i]}" || { RES[$i]="skipped (BOARD_HOST in sites/$n.conf is not a Tailscale address: use the board's Tailscale address, 100.64.0.0 to 100.127.255.255)"; continue; }
  case "${USERS[$i]}" in ""|*[!a-zA-Z0-9._-]*) RES[$i]="skipped (BOARD_USER in sites/$n.conf is not usable)"; continue;; esac
  KEYS[$i]="$(ssh -o BatchMode=yes $O "${USERS[$i]}@${HOSTS[$i]}" 'cat ~/netmon/data/token' 2>/dev/null)"
  case "${KEYS[$i]}" in *[!A-Za-z0-9_-]*) KEYS[$i]="";; esac
  [ "${#KEYS[$i]}" -ge 8 ] || { KEYS[$i]=""; RES[$i]="failed (cannot read the access key over SSH)"; }
done
# 2. all or nothing: one site that failed stops everything before anything is written
BAD=0
for i in "${!NAMES[@]}"; do [ "${RES[$i]}" = ok ] || BAD=1; done
if [ "$BAD" = 1 ]; then
  KEYS=()
  mkdir -p "$OUTDIR"
  { date; for i in "${!NAMES[@]}"; do echo "${NAMES[$i]}: ${RES[$i]}"; done; echo "Nothing was written to any board. Fix the site(s) above, then run this again."; } | tee "$OUT"
  exit 1
fi
# 3. each board gets the list of all the others, then restarts
STOP=0
for i in "${!NAMES[@]}"; do
  if [ "$STOP" = 1 ]; then RES[$i]="not written (stopped after an earlier failure)"; continue; fi
  J="{\"site\": \"${NAMES[$i]}\", \"peers\": ["; sep=""
  for j in "${!NAMES[@]}"; do
    [ "$j" != "$i" ] || continue
    J="$J$sep{\"name\": \"${NAMES[$j]}\", \"url\": \"http://${HOSTS[$j]}:8080\", \"key\": \"${KEYS[$j]}\"}"; sep=", "
  done
  J="$J]}"
  T="${USERS[$i]}@${HOSTS[$i]}"
  echo "Linking ${NAMES[$i]} ..."
  if printf '%s\n' "$J" | ssh $O "$T" 'umask 077; cat > ~/netmon/data/peers.json.new && chmod 600 ~/netmon/data/peers.json.new && mv ~/netmon/data/peers.json.new ~/netmon/data/peers.json' 2>/dev/null; then
    ssh -t $O "$T" 'sudo systemctl restart overheard.service' || { RES[$i]="written, but the service did not restart: is it installed as a service?"; STOP=1; }
  else
    RES[$i]="failed (cannot write peers.json; nothing written on this board)"; STOP=1
  fi
done
J=""; KEYS=()
mkdir -p "$OUTDIR"
{ date; for i in "${!NAMES[@]}"; do echo "${NAMES[$i]}: ${RES[$i]}"; done
  [ "$STOP" = 1 ] && echo "Stopped part-way: boards marked ok already have the new list, the others were left as they were. Fix the failing board, then run this again."; } | tee "$OUT"
echo
echo "Saved to $OUT. Open a board's dashboard: the site buttons appear at the top."
for i in "${!NAMES[@]}"; do [ "${RES[$i]}" = ok ] || exit 1; done
