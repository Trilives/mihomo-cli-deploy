#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE_DIR="${ROOT_DIR}/source"
DOWNLOAD_DIR="${SOURCE_DIR}/downloads"

META_RULES_REPO="MetaCubeX/meta-rules-dat"
MIHOMO_REPO="MetaCubeX/mihomo"
UI_REPO="MetaCubeX/metacubexd"

# GitHub token (optional): authenticates API calls to raise the rate limit from
# 60/hour to 5000/hour and avoid 403. Priority: existing GITHUB_TOKEN/GH_TOKEN
# env var, then a GITHUB_TOKEN entry in <root>/.env.
GITHUB_TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
ENV_FILE="${ROOT_DIR}/.env"
if [[ -z "${GITHUB_TOKEN}" && -f "${ENV_FILE}" ]]; then
  GITHUB_TOKEN="$(sed -nE 's/^[[:space:]]*(GITHUB_TOKEN|GH_TOKEN)[[:space:]]*=[[:space:]]*"?([^"[:space:]]+)"?.*$/\2/p' "${ENV_FILE}" | head -n1)"
fi
GH_AUTH_HEADER=()
if [[ -n "${GITHUB_TOKEN}" ]]; then
  GH_AUTH_HEADER=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
fi

env_value() {
  local key_regex="$1"
  [[ -f "${ENV_FILE}" ]] || return 0
  sed -nE "s/^[[:space:]]*(${key_regex})[[:space:]]*=[[:space:]]*\"?([^\"[:space:]]+)\"?.*$/\\2/p" "${ENV_FILE}" | head -n1
}

# Download proxy (optional): point this at a proxy reachable on your LAN so the
# update can fetch GitHub through a device that already has good connectivity,
# for example http://192.168.2.7:7897 or socks5h://192.168.2.7:7897. Priority:
# DOWNLOAD_PROXY env var, then standard *_PROXY env vars, then a DOWNLOAD_PROXY
# entry in <root>/.env.
DOWNLOAD_PROXY="${DOWNLOAD_PROXY:-${ALL_PROXY:-${all_proxy:-${HTTPS_PROXY:-${https_proxy:-${HTTP_PROXY:-${http_proxy:-}}}}}}}"
if [[ -z "${DOWNLOAD_PROXY}" ]]; then
  DOWNLOAD_PROXY="$(env_value 'DOWNLOAD_PROXY')"
fi

CURL_COMMON_ARGS=(
  -fL
  --retry 3
  --connect-timeout 10
)

# Probe whether a direct (proxy-bypassing) connection to the public internet
# works, by hitting Google's generate_204 endpoint. The result is memoized so
# the probe runs at most once per invocation.
GOOGLE_PROBE_URL="https://www.google.com/generate_204"
DIRECT_REACHABLE=""  # empty = not probed yet; 0 = direct works; 1 = blocked
direct_reachable() {
  if [[ -z "${DIRECT_REACHABLE}" ]]; then
    if curl -fsS --noproxy '*' --connect-timeout 5 --max-time 10 \
        -o /dev/null "${GOOGLE_PROBE_URL}"; then
      DIRECT_REACHABLE=0
      echo "Direct connection to Google works; skipping proxy." >&2
    else
      DIRECT_REACHABLE=1
    fi
  fi
  return "${DIRECT_REACHABLE}"
}

# Decide which "channels" curl should try, in order. With a proxy configured we
# normally try it first and fall back to a direct connection, so a flaky proxy
# never blocks the update. But if a direct connection to Google already works we
# skip the proxy entirely. Without a proxy (or with MIHOMO_NO_PROXY=1) we go
# direct only.
curl_channels() {
  if [[ -n "${DOWNLOAD_PROXY}" && "${MIHOMO_NO_PROXY:-0}" != "1" ]] \
      && ! direct_reachable; then
    printf '%s\n' proxy direct
  else
    printf '%s\n' direct
  fi
}

# Run curl with the common args plus any extra args, attempting each channel in
# turn. Returns success on the first channel that works.
curl_fetch() {
  local -a channels
  mapfile -t channels < <(curl_channels)
  local last_index=$(( ${#channels[@]} - 1 ))
  local i rc=0
  for i in "${!channels[@]}"; do
    local -a channel_args=()
    case "${channels[i]}" in
      proxy) channel_args=(--proxy "${DOWNLOAD_PROXY}") ;;
      direct) [[ -n "${DOWNLOAD_PROXY}" ]] && channel_args=(--noproxy '*') ;;
    esac
    if curl "${CURL_COMMON_ARGS[@]}" "${channel_args[@]}" "$@"; then
      return 0
    fi
    rc=$?
    if [[ "${i}" -lt "${last_index}" ]]; then
      echo "  ${channels[i]} connection failed (curl exit ${rc}); retrying direct..." >&2
    fi
  done
  return "${rc}"
}

curl_read() {
  curl_fetch -sS ${GH_AUTH_HEADER[@]+"${GH_AUTH_HEADER[@]}"} "$@"
}

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
     - mihomo.version
     - ui/

Options:
  --variant  Prefer a mihomo build variant: standard (default) or compatible.
             Use compatible for older CPUs without modern instruction sets.

Environment:
  MIHOMO_VARIANT  Same as --variant when the option is omitted.
  DOWNLOAD_PROXY  Optional curl proxy URL, for example:
                  http://192.168.2.7:7897 or socks5h://192.168.2.7:7897.
                  May also be set as DOWNLOAD_PROXY in <root>/.env. When set,
                  downloads try the proxy first and fall back to a direct
                  connection — unless a direct connection to Google already
                  works, in which case the proxy is skipped.
  MIHOMO_NO_PROXY=1
                  Force direct connections and ignore any configured proxy.
EOF
}

MIHOMO_VARIANT="${MIHOMO_VARIANT:-standard}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --variant)
      if [[ $# -lt 2 ]]; then
        echo "Error: --variant requires standard or compatible" >&2
        exit 1
      fi
      MIHOMO_VARIANT="$2"
      shift 2
      ;;
    *)
      echo "Error: unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

case "${MIHOMO_VARIANT}" in
  standard|compatible) ;;
  *)
    echo "Error: --variant must be standard or compatible" >&2
    exit 1
    ;;
esac

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
  x86_64) MIHOMO_ARCH="amd64" ;;
  aarch64|arm64) MIHOMO_ARCH="arm64" ;;
  armv7l|armv7) MIHOMO_ARCH="armv7" ;;
  armv6l|armv6) MIHOMO_ARCH="armv6" ;;
  i386|i686) MIHOMO_ARCH="386" ;;
  riscv64) MIHOMO_ARCH="riscv64" ;;
  s390x) MIHOMO_ARCH="s390x" ;;
  *) MIHOMO_ARCH="${ARCH}" ;;
esac

if [[ -n "${DOWNLOAD_PROXY}" ]]; then
  echo "Using download proxy: ${DOWNLOAD_PROXY}"
fi

api_assets() {
  local repo="$1"
  local api_url="https://api.github.com/repos/${repo}/releases/latest"
  curl_read "${api_url}" \
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
  curl_fetch -o "${out}" "${url}"
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

echo "Step 2/4: Download mihomo binary (${MIHOMO_ARCH}, variant: ${MIHOMO_VARIANT})"
ARCHIVE_EXT='(\.gz|\.tgz|\.tar\.gz|\.zip)'
# mihomo publishes several amd64 builds (plain, -compatible, -go120). Anchor on
# "${MIHOMO_ARCH}-v<version>" to deterministically pick the standard build, and
# fall back to the compatible build, then to any matching arch asset.
MIHOMO_URL=""
if [[ "${MIHOMO_VARIANT}" == "compatible" ]]; then
  MIHOMO_URL="$(pick_asset "${MIHOMO_REPO}" "mihomo-linux-${MIHOMO_ARCH}-compatible-v[0-9][^/]*${ARCHIVE_EXT}$")"
fi
if [[ -z "${MIHOMO_URL}" ]]; then
  MIHOMO_URL="$(pick_asset "${MIHOMO_REPO}" "mihomo-linux-${MIHOMO_ARCH}-v[0-9][^/]*${ARCHIVE_EXT}$")"
fi
if [[ -z "${MIHOMO_URL}" ]]; then
  MIHOMO_URL="$(pick_asset "${MIHOMO_REPO}" "mihomo-linux-${MIHOMO_ARCH}-compatible-v[0-9][^/]*${ARCHIVE_EXT}$")"
fi
if [[ -z "${MIHOMO_URL}" ]]; then
  MIHOMO_URL="$(pick_asset "${MIHOMO_REPO}" "mihomo-linux-${MIHOMO_ARCH}[^/]*${ARCHIVE_EXT}$")"
fi
if [[ -z "${MIHOMO_URL}" ]]; then
  echo "Error: failed to find a Linux mihomo asset for ${MIHOMO_ARCH} from ${MIHOMO_REPO} releases" >&2
  exit 1
fi
MIHOMO_VERSION="$(printf '%s\n' "${MIHOMO_URL}" | grep -oE 'v[0-9]+(\.[0-9]+)+' | head -n 1 || true)"

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
if [[ -n "${MIHOMO_VERSION}" ]]; then
  printf '%s\n' "${MIHOMO_VERSION}" > "${ROOT_DIR}/mihomo.version"
fi

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
  if [[ -d "${candidate}/assets" || -d "${candidate}/_nuxt" ]]; then
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
[[ -n "${MIHOMO_VERSION}" ]] && echo "  - ${ROOT_DIR}/mihomo.version (${MIHOMO_VERSION})"
echo "  - ${ROOT_DIR}/ui"
echo "Downloads cached in: ${DOWNLOAD_DIR}"
"${ROOT_DIR}/mihomo" -v 2>/dev/null | head -n 1 || true
