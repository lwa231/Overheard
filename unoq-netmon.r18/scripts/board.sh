# Source me:  . "$(dirname "${BASH_SOURCE[0]}")/board.sh"   (or  . scripts/board.sh  from the project folder)
# Reads board.conf (and sites/$SITE.conf when SITE is set) and sets BOARD_USER, BOARD_HOST, BOARD_MDNS, BOARD_DEFAULT.
# Order, last wins: board.conf, sites/$SITE.conf, then BOARD_USER / BOARD_HOST / BOARD_MDNS from the environment.
# BOARD itself (user@host) is left alone: scripts keep using it as the "I was told exactly" override.
_ov_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_ov_u="${BOARD_USER:-}"; _ov_h="${BOARD_HOST:-}"; _ov_m="${BOARD_MDNS:-}"; _ov_s="${SITE:-}"
# shellcheck disable=SC1091
[ -f "$_ov_root/board.conf" ] && . "$_ov_root/board.conf"
[ -n "$_ov_s" ] && SITE="$_ov_s"
if [ -n "${SITE:-}" ]; then
  if [ -f "$_ov_root/sites/$SITE.conf" ]; then . "$_ov_root/sites/$SITE.conf"
  else echo "No such site: sites/$SITE.conf"; return 1 2>/dev/null || exit 1; fi
fi
[ -n "$_ov_u" ] && BOARD_USER="$_ov_u"
[ -n "$_ov_h" ] && BOARD_HOST="$_ov_h"
[ -n "$_ov_m" ] && BOARD_MDNS="$_ov_m"
BOARD_USER="${BOARD_USER:-arduino}"
BOARD_MDNS="${BOARD_MDNS:-}"
if [ -z "${BOARD_HOST:-}" ] || [ "$BOARD_HOST" = "CHANGE-ME" ]; then
  echo "Set BOARD_HOST in board.conf (or sites/$SITE.conf): the board's address."; return 1 2>/dev/null || exit 1
fi
BOARD_DEFAULT="$BOARD_USER@$BOARD_HOST"
unset _ov_root _ov_u _ov_h _ov_m _ov_s
