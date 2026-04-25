#!/usr/bin/env bash
set -euo pipefail

# Uninstall the user-level systemd timer and service for subscription updates.

SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

systemctl --user disable --now mihomo-subscription-update.timer >/dev/null 2>&1 || true
rm -f "${SYSTEMD_USER_DIR}/mihomo-subscription-update.timer"
rm -f "${SYSTEMD_USER_DIR}/mihomo-subscription-update.service"
systemctl --user daemon-reload

echo "[OK] Removed user timer/service for mihomo subscription updates."
