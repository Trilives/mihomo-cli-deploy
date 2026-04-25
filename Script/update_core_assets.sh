#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE_DIR="${ROOT_DIR}/source"
DOWNLOAD_DIR="${SOURCE_DIR}/downloads"

META_RULES_REPO="MetaCubeX/meta-rules-dat"
MIHOMO_REPO="MetaCubeX/mihomo"
UI_REPO="MetaCubeX/metacubexd"

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: missing command: $1" >&2
    exit 1
  fi
}

usage() {
  cat <<'EOF'
Usage:
  ./Script/update_core_assets.sh

What it does:
  1) Download country.mmdb and geoip.metadb from MetaCubeX/meta-rules-dat.
  2) Download latest Linux mihomo binary from MetaCubeX/mihomo.
  3) Download latest UI package from MetaCubeX/metacubexd.
  4) Save all downloads in source/downloads.
  5) Deploy files to workspace root:
     - country.mmdb
     - geoip.metadb
     - mihomo
     - ui/
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

need_cmd curl
need_cmd grep
need_cmd sed
need_cmd awk
need_cmd tar
need_cmd gzip
need_cmd find
need_cmd mktemp
need_cmd install

mkdir -p "${DOWNLOAD_DIR}"

ARCH="$(uname -m)"
case "${ARCH}" in
  x86_64) ARCH_PATTERN="amd64|x86_64" ;;
  aarch64|arm64) ARCH_PATTERN="arm64|aarch64" ;;
  armv7l|armv7) ARCH_PATTERN="armv7|armv7l" ;;
  *) ARCH_PATTERN="${ARCH}" ;;
esac

api_assets() {
  local repo="$1"
  local api_url="https://api.github.com/repos/${repo}/releases/latest"
  curl -fsSL "${api_url}" \
    | grep '"browser_download_url"' \
    | sed -E 's/^[[:space:]]*"browser_download_url": "([^"]+)",?$/\1/'
}

pick_asset() {
  local repo="$1"
  local regex="$2"
  api_assets "${repo}" | grep -Ei "${regex}" | head -n 1 || true
}

download_to() {
  local url="$1"
  local out="$2"
  echo "Downloading: ${url}"
  curl -fL --retry 3 --connect-timeout 10 -o "${out}" "${url}"
}

extract_archive() {
  local archive="$1"
  local out_dir="$2"
  mkdir -p "${out_dir}"

  case "${archive}" in
    *.tar.gz|*.tgz)
      tar -xzf "${archive}" -C "${out_dir}"
      ;;
    *.zip)
      if command -v unzip >/dev/null 2>&1; then
        unzip -q "${archive}" -d "${out_dir}"
      else
        echo "Error: unzip is required to extract ${archive}" >&2
        exit 1
      fi
      ;;
    *.gz)
      gzip -dc "${archive}" > "${out_dir}/$(basename "${archive%.gz}")"
      ;;
    *)
      cp "${archive}" "${out_dir}/"
      ;;
  esac
}

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

echo "Step 1/4: Download meta-rules data"
COUNTRY_URL="https://github.com/${META_RULES_REPO}/releases/latest/download/country.mmdb"
GEOIP_META_URL="https://github.com/${META_RULES_REPO}/releases/latest/download/geoip.metadb"

COUNTRY_FILE="${DOWNLOAD_DIR}/country.mmdb"
GEOIP_META_FILE="${DOWNLOAD_DIR}/geoip.metadb"

download_to "${COUNTRY_URL}" "${COUNTRY_FILE}"
download_to "${GEOIP_META_URL}" "${GEOIP_META_FILE}"

install -m 0644 "${COUNTRY_FILE}" "${ROOT_DIR}/country.mmdb"
install -m 0644 "${GEOIP_META_FILE}" "${ROOT_DIR}/geoip.metadb"

echo "Step 2/4: Download mihomo binary"
MIHOMO_URL="$(pick_asset "${MIHOMO_REPO}" "linux.*(${ARCH_PATTERN}).*(\\.gz|\\.tgz|\\.tar\\.gz|\\.zip)$")"
if [[ -z "${MIHOMO_URL}" ]]; then
  MIHOMO_URL="$(pick_asset "${MIHOMO_REPO}" "linux.*(\\.gz|\\.tgz|\\.tar\\.gz|\\.zip)$")"
fi
if [[ -z "${MIHOMO_URL}" ]]; then
  echo "Error: failed to find a Linux mihomo asset from ${MIHOMO_REPO} releases" >&2
  exit 1
fi

MIHOMO_ARCHIVE="${DOWNLOAD_DIR}/$(basename "${MIHOMO_URL}")"
download_to "${MIHOMO_URL}" "${MIHOMO_ARCHIVE}"

MIHOMO_EXTRACT_DIR="${TMP_DIR}/mihomo"
extract_archive "${MIHOMO_ARCHIVE}" "${MIHOMO_EXTRACT_DIR}"

MIHOMO_BIN="$(find "${MIHOMO_EXTRACT_DIR}" -type f \( -name 'mihomo*' -o -name 'clash*' \) | head -n 1 || true)"
if [[ -z "${MIHOMO_BIN}" ]]; then
  MIHOMO_BIN="$(find "${MIHOMO_EXTRACT_DIR}" -type f | head -n 1 || true)"
fi
if [[ -z "${MIHOMO_BIN}" ]]; then
  echo "Error: failed to locate mihomo binary after extracting ${MIHOMO_ARCHIVE}" >&2
  exit 1
fi

install -m 0755 "${MIHOMO_BIN}" "${ROOT_DIR}/mihomo"

echo "Step 3/4: Download UI package"
UI_URL="$(pick_asset "${UI_REPO}" "(gh-pages|dist).*(\\.zip|\\.tar\\.gz|\\.tgz)$")"
if [[ -z "${UI_URL}" ]]; then
  UI_URL="$(pick_asset "${UI_REPO}" "(\\.zip|\\.tar\\.gz|\\.tgz)$")"
fi
if [[ -z "${UI_URL}" ]]; then
  echo "Error: failed to find a UI asset from ${UI_REPO} releases" >&2
  exit 1
fi

UI_ARCHIVE="${DOWNLOAD_DIR}/$(basename "${UI_URL}")"
download_to "${UI_URL}" "${UI_ARCHIVE}"

UI_EXTRACT_DIR="${TMP_DIR}/ui"
extract_archive "${UI_ARCHIVE}" "${UI_EXTRACT_DIR}"

UI_ROOT=""
while IFS= read -r idx; do
  candidate="$(dirname "${idx}")"
  if [[ -d "${candidate}/_nuxt" ]]; then
    UI_ROOT="${candidate}"
    break
  fi
done < <(find "${UI_EXTRACT_DIR}" -type f -name 'index.html')

if [[ -z "${UI_ROOT}" ]]; then
  first_index="$(find "${UI_EXTRACT_DIR}" -type f -name 'index.html' | head -n 1 || true)"
  if [[ -n "${first_index}" ]]; then
    UI_ROOT="$(dirname "${first_index}")"
  fi
fi

if [[ -z "${UI_ROOT}" ]]; then
  echo "Error: failed to locate UI root directory from ${UI_ARCHIVE}" >&2
  exit 1
fi

echo "Step 4/4: Deploy UI to ${ROOT_DIR}/ui"
rm -rf "${ROOT_DIR}/ui"
mkdir -p "${ROOT_DIR}/ui"
cp -a "${UI_ROOT}/." "${ROOT_DIR}/ui/"

echo "Done. Updated files:"
echo "  - ${ROOT_DIR}/country.mmdb"
echo "  - ${ROOT_DIR}/geoip.metadb"
echo "  - ${ROOT_DIR}/mihomo"
echo "  - ${ROOT_DIR}/ui"
echo "Downloads cached in: ${DOWNLOAD_DIR}"
