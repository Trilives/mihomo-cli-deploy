#!/usr/bin/env bash
set -euo pipefail

# Download subscription and convert to mihomo config format.
# Usage:
#   ./convert_subscription_to_config.sh "https://example.com/sub" "/path/to/out.yaml"
#   SUBSCRIPTION_URL="https://example.com/sub" ./convert_subscription_to_config.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RAW_FILE="$(mktemp "${BASE_DIR}/subscription.raw.XXXXXX")"
OUT_PATH="${2:-${BASE_DIR}/config.converted.yaml}"
TEMPLATE_PATH="${BASE_DIR}/config.yaml"
PROCESSOR="${SCRIPT_DIR}/process_subscription.py"
SUB_URL="${1:-${SUBSCRIPTION_URL:-}}"

cleanup() {
  rm -f "${RAW_FILE}"
}
trap cleanup EXIT

if [[ -z "${SUB_URL}" ]]; then
  echo "[ERROR] Missing subscription URL."
  echo "Set SUBSCRIPTION_URL env or pass it as first arg."
  exit 1
fi

echo "[INFO] Downloading subscription..."
if command -v curl >/dev/null 2>&1; then
  curl -fsSL --connect-timeout 10 --max-time 60 \
    -H "User-Agent: mihomo-config-converter/1.0" \
    "${SUB_URL}" -o "${RAW_FILE}"
elif command -v wget >/dev/null 2>&1; then
  wget -qO "${RAW_FILE}" "${SUB_URL}"
else
  echo "[ERROR] Neither curl nor wget is installed."
  exit 1
fi

if [[ ! -s "${RAW_FILE}" ]]; then
  echo "[ERROR] Downloaded content is empty."
  exit 1
fi

echo "[INFO] Converting subscription to config..."
python3 "${PROCESSOR}" --input "${RAW_FILE}" --template "${TEMPLATE_PATH}" --output "${OUT_PATH}"

echo "[OK] Converted config saved to: ${OUT_PATH}"
