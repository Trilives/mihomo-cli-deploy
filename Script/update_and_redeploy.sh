#!/usr/bin/env bash

# Update the mihomo core, Web UI, and geo databases, then reinstall and restart
# the systemd service so the new binary and assets take effect. Intended to be
# driven by the weekly systemd timer, but also safe to run by hand. Any extra
# arguments are forwarded to update_core_assets.sh (for example: --variant
# compatible).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

log "Step 1/2: update mihomo core, Web UI, and geo databases"
"${SCRIPT_DIR}/update_core_assets.sh" "$@"

log "Step 2/2: reinstall and restart the systemd service"
"${SCRIPT_DIR}/setup_mihomo_service.sh"

log "Done: core, UI, and geo databases updated; service redeployed"
