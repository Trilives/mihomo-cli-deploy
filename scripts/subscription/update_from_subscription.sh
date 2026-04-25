#!/usr/bin/env bash
set -euo pipefail

# Pull mihomo config from a subscription URL, validate, then atomically replace.
# Usage:
#   SUBSCRIPTION_URL="https://example.com/sub" ./update_from_subscription.sh
#   ./update_from_subscription.sh "https://example.com/sub"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONFIG_PATH="${BASE_DIR}/config.yaml"
MIHOMO_BIN="${BASE_DIR}/mihomo"
BACKUP_DIR="${BASE_DIR}/backups"
RAW_FILE="$(mktemp "${BASE_DIR}/subscription.raw.XXXXXX")"
TMP_FILE="$(mktemp "${BASE_DIR}/config.yaml.new.XXXXXX")"
PROCESSOR="${SCRIPT_DIR}/process_subscription.py"

SUB_URL="${1:-${SUBSCRIPTION_URL:-}}"
if [[ -z "${SUB_URL}" ]]; then
  echo "[ERROR] Missing subscription URL."
  echo "Set SUBSCRIPTION_URL env or pass it as first arg."
  exit 1
fi

mkdir -p "${BACKUP_DIR}"

echo "[INFO] Downloading subscription config..."
if command -v curl >/dev/null 2>&1; then
  curl -fsSL --connect-timeout 10 --max-time 60 \
    -H "User-Agent: mihomo-config-updater/1.0" \
    "${SUB_URL}" -o "${RAW_FILE}"
elif command -v wget >/dev/null 2>&1; then
  wget -qO "${RAW_FILE}" "${SUB_URL}"
else
  echo "[ERROR] Neither curl nor wget is installed."
  rm -f "${RAW_FILE}" "${TMP_FILE}"
  exit 1
fi

if [[ ! -s "${RAW_FILE}" ]]; then
  echo "[ERROR] Downloaded file is empty."
  rm -f "${RAW_FILE}" "${TMP_FILE}"
  exit 1
fi

if [[ ! -x "${MIHOMO_BIN}" ]]; then
  echo "[ERROR] mihomo binary not found or not executable: ${MIHOMO_BIN}"
  rm -f "${RAW_FILE}" "${TMP_FILE}"
  exit 1
fi

if [[ ! -f "${PROCESSOR}" ]]; then
  echo "[ERROR] Missing processor script: ${PROCESSOR}"
  rm -f "${RAW_FILE}" "${TMP_FILE}"
  exit 1
fi

echo "[INFO] Processing subscription into config format..."
if ! python3 "${PROCESSOR}" --input "${RAW_FILE}" --template "${CONFIG_PATH}" --output "${TMP_FILE}"; then
  echo "[ERROR] Failed to process subscription content."
  rm -f "${RAW_FILE}" "${TMP_FILE}"
  exit 1
fi

echo "[INFO] Validating new config with mihomo..."
if ! "${MIHOMO_BIN}" -t -f "${TMP_FILE}" >/dev/null 2>&1; then
  echo "[ERROR] New config validation failed, keeping current config."
  rm -f "${RAW_FILE}" "${TMP_FILE}"
  exit 1
fi

TS="$(date +%Y%m%d_%H%M%S)"
if [[ -f "${CONFIG_PATH}" ]]; then
  cp -f "${CONFIG_PATH}" "${BACKUP_DIR}/config.yaml.bak.${TS}"
  echo "[INFO] Backup saved: ${BACKUP_DIR}/config.yaml.bak.${TS}"
fi

mv -f "${TMP_FILE}" "${CONFIG_PATH}"
rm -f "${RAW_FILE}"
echo "[INFO] Config replaced: ${CONFIG_PATH}"

if command -v systemctl >/dev/null 2>&1; then
  # Try reloading common service names; ignore failure to keep script portable.
  if systemctl --user is-active --quiet mihomo.service; then
    systemctl --user restart mihomo.service || true
    echo "[INFO] Restarted user service: mihomo.service"
  elif systemctl is-active --quiet mihomo.service; then
    sudo systemctl restart mihomo.service || true
    echo "[INFO] Restarted system service: mihomo.service"
  fi
fi

echo "[OK] Subscription update completed."
