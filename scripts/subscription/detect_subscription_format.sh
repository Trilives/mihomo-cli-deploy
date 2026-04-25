#!/usr/bin/env bash
set -euo pipefail

# Detect whether a subscription URL is clash yaml or base links.
# Usage:
#   ./detect_subscription_format.sh "https://example.com/sub"
#   SUBSCRIPTION_URL="https://example.com/sub" ./detect_subscription_format.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAW_FILE="$(mktemp)"
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

echo "[INFO] Downloading subscription..." >&2
if command -v curl >/dev/null 2>&1; then
  curl -fsSL --connect-timeout 10 --max-time 60 \
    -H "User-Agent: mihomo-format-detector/1.0" \
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

python3 "${PROCESSOR}" --input "${RAW_FILE}" --detect-only
