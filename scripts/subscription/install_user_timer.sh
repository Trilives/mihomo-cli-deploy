#!/usr/bin/env bash
set -euo pipefail

# Install a user-level systemd timer for auto-updating mihomo config.
# Usage:
#   SUBSCRIPTION_URL="https://example.com/sub" ./install_user_timer.sh
#   ./install_user_timer.sh "https://example.com/sub"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPDATE_SCRIPT="${SCRIPT_DIR}/update_from_subscription.sh"
SUB_URL="${1:-${SUBSCRIPTION_URL:-}}"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

if [[ -z "${SUB_URL}" ]]; then
  echo "[ERROR] Missing subscription URL."
  echo "Set SUBSCRIPTION_URL env or pass it as first arg."
  exit 1
fi

mkdir -p "${SYSTEMD_USER_DIR}"

# systemd unit values treat % as a specifier marker; escape it to keep URL literal.
SUB_URL_ESCAPED="${SUB_URL//%/%%}"

cat > "${SYSTEMD_USER_DIR}/mihomo-subscription-update.service" <<EOF
[Unit]
Description=Update Mihomo config from subscription URL
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
Environment=SUBSCRIPTION_URL=${SUB_URL_ESCAPED}
ExecStart=${UPDATE_SCRIPT}
EOF

cat > "${SYSTEMD_USER_DIR}/mihomo-subscription-update.timer" <<'EOF'
[Unit]
Description=Run Mihomo subscription updater every 6 hours

[Timer]
OnBootSec=3min
OnUnitActiveSec=6h
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now mihomo-subscription-update.timer

echo "[OK] Installed and started user timer: mihomo-subscription-update.timer"
echo "Check status with: systemctl --user status mihomo-subscription-update.timer"
