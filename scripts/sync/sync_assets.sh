#!/usr/bin/env bash
set -euo pipefail

# Sync ignored binary assets from official upstreams.
# - Geo data source: https://github.com/Loyalsoldier/geoip
# - Mihomo source:   https://github.com/MetaCubeX/mihomo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TMP_DIR="$(mktemp -d)"
GEO_BASE="https://github.com/Loyalsoldier/geoip/releases/latest/download"
MIHOMO_API="https://api.github.com/repos/MetaCubeX/mihomo/releases/latest"

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

download() {
  local url="$1"
  local out="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --connect-timeout 15 --max-time 180 "$url" -o "$out"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$out" "$url"
  else
    echo "[ERROR] Neither curl nor wget is installed." >&2
    exit 1
  fi
}

echo "[INFO] Syncing geo data from Loyalsoldier/geoip..."
download "${GEO_BASE}/Country.mmdb" "${TMP_DIR}/Country.mmdb"
download "${GEO_BASE}/geoip.dat" "${TMP_DIR}/geoip.dat"

install -m 0644 "${TMP_DIR}/Country.mmdb" "${BASE_DIR}/Country.mmdb"
install -m 0644 "${TMP_DIR}/geoip.dat" "${BASE_DIR}/geoip.dat"

echo "[INFO] Resolving latest Mihomo linux-amd64 release asset..."
download "${MIHOMO_API}" "${TMP_DIR}/mihomo_release.json"
MIHOMO_URL="$(python3 - <<'PY' "${TMP_DIR}/mihomo_release.json"
import json
import re
import sys

with open(sys.argv[1], 'r', encoding='utf-8') as f:
    data = json.load(f)

assets = data.get('assets', [])
patterns = [
    re.compile(r'mihomo-linux-amd64.*\\.gz$'),
    re.compile(r'mihomo-linux-amd64.*$'),
]

for pat in patterns:
    for a in assets:
        name = a.get('name', '')
        url = a.get('browser_download_url', '')
        if pat.search(name):
            print(url)
            raise SystemExit(0)

raise SystemExit(1)
PY
)" || {
  echo "[ERROR] Failed to find linux-amd64 Mihomo asset from latest release." >&2
  exit 1
}

ASSET_NAME="${MIHOMO_URL##*/}"
echo "[INFO] Downloading Mihomo asset: ${ASSET_NAME}"
download "${MIHOMO_URL}" "${TMP_DIR}/${ASSET_NAME}"

if [[ "${ASSET_NAME}" == *.gz ]]; then
  gunzip -f "${TMP_DIR}/${ASSET_NAME}"
  BIN_PATH="${TMP_DIR}/${ASSET_NAME%.gz}"
else
  BIN_PATH="${TMP_DIR}/${ASSET_NAME}"
fi

install -m 0755 "${BIN_PATH}" "${BASE_DIR}/mihomo"

echo "[OK] Assets synced:"
echo "  - ${BASE_DIR}/Country.mmdb"
echo "  - ${BASE_DIR}/geoip.dat"
echo "  - ${BASE_DIR}/mihomo"
