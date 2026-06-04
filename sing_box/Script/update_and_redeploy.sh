#!/usr/bin/env bash

# Update the sing-box core, Web UI, and CN rule sets, then reinstall and
# restart the systemd service so the new binary and rule sets take effect.
# Intended to be driven by the weekly systemd timer, but also safe to run by
# hand. Any extra arguments are forwarded to update_sing_box_core.sh
# (for example: --libc musl).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

log "Step 1/2: update sing-box core, Web UI, and CN rule sets"
"${SCRIPT_DIR}/update_sing_box_core.sh" "$@"

log "Step 2/2: reinstall and restart the systemd service"
"${SCRIPT_DIR}/setup_sing_box_service.sh"

log "Done: core, UI, and rule sets updated; service redeployed"
