#!/usr/bin/env bash
# One time only. Lets this Mac log into the board without a password, and lets the program use DNS port 53.
set -e
BOARD="${BOARD:-arduino@100.69.33.51}"
O="-o StrictHostKeyChecking=accept-new"
[ -f ~/.ssh/id_ed25519 ] || ssh-keygen -q -t ed25519 -N "" -f ~/.ssh/id_ed25519
echo "Board password (1 of 2):"
ssh $O "$BOARD" 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys' < ~/.ssh/id_ed25519.pub
echo "Board password again, for sudo (2 of 2):"
ssh -t $O "$BOARD" "echo 'net.ipv4.ip_unprivileged_port_start=53' | sudo tee /etc/sysctl.d/99-overheard.conf >/dev/null && sudo sysctl -q --system && mkdir -p ~/netmon"
echo "Done. From now on open Overheard.app, or run:  ./scripts/run.sh"
