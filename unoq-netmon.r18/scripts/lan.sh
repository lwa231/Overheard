# Source me:  . "$(dirname "${BASH_SOURCE[0]}")/lan.sh"
# Address checks shared by install.sh (BOARD_LAN_IP -> --expect-ip) and net_static.sh. Pure bash, no output, return 0 = valid.
#   ip_ok a.b.c.d            dotted IPv4, each part 0-255, no leading zeros
#   lan_cidr_ok a.b.c.d/NN   a host address (not network/broadcast) with a prefix length of 8 to 30
#   lan_gw_ok CIDR GATEWAY   gateway is an IPv4 address in the same subnet, not the board's own address, not the network or broadcast address
ip_ok() {
  local IFS=.; local -a o=($1); [ "${#o[@]}" -eq 4 ] || return 1
  local x
  for x in "${o[@]}"; do
    case "$x" in ""|*[!0-9]*) return 1;; esac
    [ "${#x}" -le 3 ] && [ "$x" -le 255 ] || return 1
    { [ "${#x}" -gt 1 ] && [ "${x:0:1}" = 0 ]; } && return 1
  done
  return 0
}
_ip2int() { local IFS=.; set -- $1; echo $(( ($1 << 24) + ($2 << 16) + ($3 << 8) + $4 )); }
lan_cidr_ok() {
  case "$1" in */*) ;; *) return 1;; esac
  local p="${1#*/}"
  case "$p" in ""|*[!0-9]*) return 1;; esac
  { [ "${#p}" -le 2 ] && [ "$p" -ge 8 ] && [ "$p" -le 30 ]; } || return 1
  ip_ok "${1%/*}" || return 1
  local h=$(( $(_ip2int "${1%/*}") & ~(0xFFFFFFFF << (32 - p)) & 0xFFFFFFFF ))     # host bits: not the network or the broadcast address
  [ "$h" -ne 0 ] && [ "$h" -ne $(( ~(0xFFFFFFFF << (32 - p)) & 0xFFFFFFFF )) ]
}
lan_gw_ok() {
  lan_cidr_ok "$1" && ip_ok "$2" || return 1
  local ip="${1%/*}" p="${1#*/}" m a g
  m=$(( (0xFFFFFFFF << (32 - p)) & 0xFFFFFFFF ))
  a=$(_ip2int "$ip"); g=$(_ip2int "$2")
  [ "$g" -ne "$a" ] || return 1
  [ $(( a & m )) -eq $(( g & m )) ] || return 1
  [ $(( g & ~m & 0xFFFFFFFF )) -ne 0 ] && [ $(( g & ~m & 0xFFFFFFFF )) -ne $(( ~m & 0xFFFFFFFF )) ]
}
