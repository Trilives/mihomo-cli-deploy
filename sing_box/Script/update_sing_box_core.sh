#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SING_BOX_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE_DIR="${SING_BOX_DIR}/source"
DOWNLOAD_DIR="${SOURCE_DIR}/downloads"
UI_DIR="${SING_BOX_DIR}/ui"
RULESET_DIR="${SING_BOX_DIR}/ruleset"

SING_BOX_REPO="SagerNet/sing-box"
UI_REPO="MetaCubeX/metacubexd"
LIBC_VARIANT="${SING_BOX_LIBC:-glibc}"
GEOSITE_CN_URL="https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-cn.srs"
GEOIP_CN_URL="https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/geoip-cn.srs"

# GitHub token (optional): authenticates API calls to raise the rate limit from
# 60/hour to 5000/hour and avoid 403. Priority: existing GITHUB_TOKEN/GH_TOKEN
# env var, then a GITHUB_TOKEN entry in the repo-root .env.
REPO_ROOT="$(cd "${SING_BOX_DIR}/.." && pwd)"
GITHUB_TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
ENV_FILE="${REPO_ROOT}/.env"
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
# entry in the repo-root .env.
DOWNLOAD_PROXY="${DOWNLOAD_PROXY:-${ALL_PROXY:-${all_proxy:-${HTTPS_PROXY:-${https_proxy:-${HTTP_PROXY:-${http_proxy:-}}}}}}}"
if [[ -z "${DOWNLOAD_PROXY}" ]]; then
  DOWNLOAD_PROXY="$(env_value 'DOWNLOAD_PROXY')"
fi

CURL_COMMON_ARGS=(
  -fL
  --retry 5
  --retry-delay 2
  --retry-all-errors
  --connect-timeout 10
  --speed-time 30
  --speed-limit 1024
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
# skip the proxy entirely. Without a proxy (or with SING_BOX_NO_PROXY=1) we go
# direct only.
curl_channels() {
  if [[ -n "${DOWNLOAD_PROXY}" && "${SING_BOX_NO_PROXY:-0}" != "1" ]] \
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
  ./sing_box/Script/update_sing_box_core.sh [--libc glibc|musl|any]

What it does:
  1) Download the latest Linux sing-box binary from SagerNet/sing-box.
  2) Download the latest MetaCubeXD Web UI package.
  3) Download official SagerNet CN rule sets:
      - SagerNet/sing-geosite: geosite-cn.srs
      - SagerNet/sing-geoip: geoip-cn.srs
  4) Save all downloads in sing_box/source/downloads.
  5) Deploy sing-box files to workspace sing_box/:
      - sing-box
      - sing-box.version
      - ruleset/geosite-cn.srs
      - ruleset/geoip-cn.srs
      - ui/

Options:
  --libc  Prefer a libc-specific Linux build. Defaults to glibc.
          Use musl for Alpine/static-like environments, or any to prefer the
          generic build when available.

Environment:
  SING_BOX_LIBC  Same as --libc when the option is omitted.
  DOWNLOAD_PROXY Optional curl proxy URL, for example:
                 http://192.168.2.7:7897 or socks5h://192.168.2.7:7897.
                 Typically a proxy shared by another device on your LAN.
                 May also be set as DOWNLOAD_PROXY in the repo-root .env file.
                 When set, downloads try the proxy first and fall back to a
                 direct connection — unless a direct connection to Google
                 already works, in which case the proxy is skipped.
  SING_BOX_NO_PROXY=1
                 Force direct connections and ignore any configured proxy.
  SING_BOX_FORCE_DOWNLOAD=1
                 Ignore cached files in sing_box/source/downloads.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --libc)
      if [[ $# -lt 2 ]]; then
        echo "Error: --libc requires glibc, musl, or any" >&2
        exit 1
      fi
      LIBC_VARIANT="$2"
      shift 2
      ;;
    *)
      echo "Error: unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

case "${LIBC_VARIANT}" in
  glibc|musl|any) ;;
  *)
    echo "Error: --libc must be glibc, musl, or any" >&2
    exit 1
    ;;
esac

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

need_cmd curl
need_cmd grep
need_cmd sed
need_cmd tar
need_cmd find
need_cmd mktemp
need_cmd install
need_cmd head
need_cmd cp
need_cmd rm

mkdir -p "${DOWNLOAD_DIR}"
mkdir -p "${SING_BOX_DIR}"
mkdir -p "${RULESET_DIR}"

ARCH="$(uname -m)"
case "${ARCH}" in
  x86_64) SING_BOX_ARCH="amd64" ;;
  aarch64|arm64) SING_BOX_ARCH="arm64" ;;
  armv7l|armv7) SING_BOX_ARCH="armv7" ;;
  armv6l|armv6) SING_BOX_ARCH="armv6" ;;
  i386|i686) SING_BOX_ARCH="386" ;;
  riscv64) SING_BOX_ARCH="riscv64" ;;
  s390x) SING_BOX_ARCH="s390x" ;;
  *) SING_BOX_ARCH="${ARCH}" ;;
esac

if [[ -n "${DOWNLOAD_PROXY}" ]]; then
  echo "Using download proxy: ${DOWNLOAD_PROXY}"
fi

release_json() {
  local repo="$1"
  local safe_repo="${repo//\//_}"
  local cache_file="${TMP_DIR}/${safe_repo}.latest.json"
  if [[ ! -s "${cache_file}" ]]; then
    local api_url="https://api.github.com/repos/${repo}/releases/latest"
    curl_read "${api_url}" > "${cache_file}"
  fi
  cat "${cache_file}"
}

api_assets() {
  local repo="$1"
  release_json "${repo}" \
    | grep '"browser_download_url"' \
    | sed -E 's/^[[:space:]]*"browser_download_url": "([^"]+)",?$/\1/'
}

latest_tag() {
  local repo="$1"
  release_json "${repo}" \
    | grep '"tag_name"' \
    | sed -E 's/^[[:space:]]*"tag_name": "([^"]+)",?$/\1/' \
    | head -n 1
}

pick_asset() {
  local repo="$1"
  local regex="$2"
  api_assets "${repo}" | grep -Ei "${regex}" | head -n 1 || true
}

cache_valid() {
  local file="$1"
  local name="${2:-$1}"

  [[ -s "${file}" ]] || return 1
  case "${name}" in
    *.tar.gz|*.tgz)
      tar -tzf "${file}" >/dev/null 2>&1
      ;;
    *.zip)
      command -v unzip >/dev/null 2>&1 && unzip -tq "${file}" >/dev/null 2>&1
      ;;
    *)
      return 0
      ;;
  esac
}

download_to() {
  local url="$1"
  local out="$2"
  local part="${out}.part"
  local resume_args=()

  if [[ "${SING_BOX_FORCE_DOWNLOAD:-0}" != "1" ]] && cache_valid "${out}" "${out}"; then
    echo "Using cached: ${out}"
    return 0
  fi
  if [[ -e "${out}" ]]; then
    echo "Discarding invalid cache: ${out}"
    rm -f "${out}" "${part}"
  fi
  if [[ -s "${part}" ]]; then
    resume_args=(-C -)
  fi

  echo "Downloading: ${url}"
  curl_fetch "${resume_args[@]}" -o "${part}" "${url}"
  if ! cache_valid "${part}" "${out}"; then
    echo "Error: downloaded file failed integrity check: ${out}" >&2
    exit 1
  fi
  mv -f "${part}" "${out}"
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
    *)
      echo "Error: unsupported archive format: ${archive}" >&2
      exit 1
      ;;
  esac
}

echo "Step 1/5: Find latest Linux sing-box asset"
SING_BOX_VERSION="$(latest_tag "${SING_BOX_REPO}")"
SING_BOX_URL=""
if [[ "${LIBC_VARIANT}" == "any" ]]; then
  SING_BOX_URL="$(pick_asset "${SING_BOX_REPO}" "sing-box-[^/]+-linux-${SING_BOX_ARCH}\\.tar\\.gz$")"
fi
if [[ -z "${SING_BOX_URL}" && "${LIBC_VARIANT}" != "any" ]]; then
  SING_BOX_URL="$(pick_asset "${SING_BOX_REPO}" "sing-box-[^/]+-linux-${SING_BOX_ARCH}-${LIBC_VARIANT}\\.tar\\.gz$")"
fi
if [[ -z "${SING_BOX_URL}" ]]; then
  SING_BOX_URL="$(pick_asset "${SING_BOX_REPO}" "sing-box-[^/]+-linux-${SING_BOX_ARCH}\\.tar\\.gz$")"
fi
if [[ -z "${SING_BOX_URL}" ]]; then
  SING_BOX_URL="$(pick_asset "${SING_BOX_REPO}" "sing-box-[^/]+-linux-${SING_BOX_ARCH}.*\\.tar\\.gz$")"
fi
if [[ -z "${SING_BOX_URL}" ]]; then
  echo "Error: failed to find a Linux sing-box asset for architecture ${SING_BOX_ARCH}" >&2
  exit 1
fi

SING_BOX_ARCHIVE="${DOWNLOAD_DIR}/$(basename "${SING_BOX_URL}")"
download_to "${SING_BOX_URL}" "${SING_BOX_ARCHIVE}"

echo "Step 2/5: Deploy sing-box binary"
SING_BOX_EXTRACT_DIR="${TMP_DIR}/sing-box"
mkdir -p "${SING_BOX_EXTRACT_DIR}"
tar -xzf "${SING_BOX_ARCHIVE}" -C "${SING_BOX_EXTRACT_DIR}"

SING_BOX_BIN="$(find "${SING_BOX_EXTRACT_DIR}" -type f -name 'sing-box' | head -n 1 || true)"
if [[ -z "${SING_BOX_BIN}" ]]; then
  echo "Error: failed to locate sing-box binary after extracting ${SING_BOX_ARCHIVE}" >&2
  exit 1
fi

install -m 0755 "${SING_BOX_BIN}" "${SING_BOX_DIR}/sing-box"
printf '%s\n' "${SING_BOX_VERSION}" > "${SING_BOX_DIR}/sing-box.version"

echo "Step 3/5: Download official CN rule sets"
GEOSITE_CN_DOWNLOAD="${DOWNLOAD_DIR}/geosite-cn.srs"
GEOIP_CN_DOWNLOAD="${DOWNLOAD_DIR}/geoip-cn.srs"
download_to "${GEOSITE_CN_URL}" "${GEOSITE_CN_DOWNLOAD}"
download_to "${GEOIP_CN_URL}" "${GEOIP_CN_DOWNLOAD}"
install -m 0644 "${GEOSITE_CN_DOWNLOAD}" "${RULESET_DIR}/geosite-cn.srs"
install -m 0644 "${GEOIP_CN_DOWNLOAD}" "${RULESET_DIR}/geoip-cn.srs"

echo "Step 4/5: Download latest Web UI asset"
UI_URL="$(pick_asset "${UI_REPO}" "(gh-pages|dist).*(\.zip|\.tar\.gz|\.tgz)$")"
if [[ -z "${UI_URL}" ]]; then
  UI_URL="$(pick_asset "${UI_REPO}" "(\.zip|\.tar\.gz|\.tgz)$")"
fi
if [[ -z "${UI_URL}" ]]; then
  echo "Error: failed to find a UI asset from ${UI_REPO} releases" >&2
  exit 1
fi

UI_ARCHIVE="${DOWNLOAD_DIR}/$(basename "${UI_URL}")"
download_to "${UI_URL}" "${UI_ARCHIVE}"

echo "Step 5/5: Deploy Web UI"
UI_EXTRACT_DIR="${TMP_DIR}/ui"
extract_archive "${UI_ARCHIVE}" "${UI_EXTRACT_DIR}"

UI_ROOT=""
while IFS= read -r index_file; do
  candidate="$(dirname "${index_file}")"
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

rm -rf "${UI_DIR}"
mkdir -p "${UI_DIR}"
cp -a "${UI_ROOT}/." "${UI_DIR}/"

echo "Done. Updated files:"
echo "  - ${SING_BOX_DIR}/sing-box"
echo "  - ${SING_BOX_DIR}/sing-box.version"
echo "  - ${RULESET_DIR}/geosite-cn.srs"
echo "  - ${RULESET_DIR}/geoip-cn.srs"
echo "  - ${UI_DIR}"
echo "Downloads cached in: ${DOWNLOAD_DIR}"
echo "Open UI: http://<LAN-IP>:9090/ui"
"${SING_BOX_DIR}/sing-box" version || true
