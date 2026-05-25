#!/usr/bin/env bash

set -euo pipefail

DEFAULT_BACKEND="https://api.v1.mk"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SING_BOX_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

backend="${SING_BOX_SUBCONVERTER_BACKEND:-$DEFAULT_BACKEND}"
source_url=""
converted_url=""
config_url=""
output_path="${SING_BOX_DIR}/config.json"
target="singbox"

declare -a extra_params=()

usage() {
  cat <<'EOF'
Usage:
  ./sing_box/Script/download_sing_box_subscription.sh -u <subscription-url> [options]

Options:
  -u, --url <url>          Original subscription URL (required)
      --converted-url <url> Full subconverter URL; target will be replaced with singbox
  -b, --backend <url>      subconverter backend URL, default: https://api.v1.mk
  -t, --target <target>    subconverter target, default: singbox
  -c, --config <url>       Remote subconverter external config URL (optional)
  -o, --output <path>      Output path, default: sing_box/config.json
  -p, --param <k=v>        Extra subconverter parameter, repeatable
  -h, --help               Show help

Examples:
  ./sing_box/Script/download_sing_box_subscription.sh -u 'https://example.com/sub?token=abc'
  ./sing_box/Script/download_sing_box_subscription.sh --converted-url 'https://backend.example/sub?target=clash&url=...'
  ./sing_box/Script/download_sing_box_subscription.sh -b 'http://127.0.0.1:25500' -u 'https://example.com/sub?token=abc'
  ./sing_box/Script/download_sing_box_subscription.sh -u 'https://example.com/sub?token=abc' -p 'udp=true' -p 'emoji=true'

Notes:
  This script calls the subconverter API:
    <backend>/sub?target=<target>&url=<encoded-subscription>

  The public web pages https://sub-web.wcc.best and https://sublink.dev are
  frontends, not guaranteed API backends. Use a real subconverter backend URL.
EOF
}

urlencode() {
  local s="$1"
  local out=""
  local i c
  LC_ALL=C
  for ((i = 0; i < ${#s}; i++)); do
    c="${s:i:1}"
    case "$c" in
      [a-zA-Z0-9.~_-]) out+="$c" ;;
      *) printf -v out '%s%%%02X' "$out" "'${c}" ;;
    esac
  done
  printf '%s' "$out"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -u|--url)
      source_url="${2:-}"
      shift 2
      ;;
    -b|--backend)
      backend="${2:-}"
      shift 2
      ;;
    --converted-url)
      converted_url="${2:-}"
      shift 2
      ;;
    -t|--target)
      target="${2:-}"
      shift 2
      ;;
    -c|--config)
      config_url="${2:-}"
      shift 2
      ;;
    -o|--output)
      output_path="${2:-}"
      shift 2
      ;;
    -p|--param)
      extra_params+=("${2:-}")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "${source_url}" && -z "${converted_url}" ]]; then
  echo "Error: missing subscription URL, use -u/--url or --converted-url" >&2
  usage >&2
  exit 1
fi

if [[ -n "${source_url}" && -n "${converted_url}" ]]; then
  echo "Error: use either -u/--url or --converted-url, not both" >&2
  exit 1
fi

if [[ -z "${target}" ]]; then
  echo "Error: target cannot be empty" >&2
  exit 1
fi

case "${backend}" in
  http://*|https://*) ;;
  *)
    echo "Error: backend must be an http(s) URL: ${backend}" >&2
    exit 1
    ;;
esac

if [[ -n "${converted_url}" ]]; then
  final_url="$(
    python3 - "${converted_url}" "${target}" <<'PY'
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import sys

url = sys.argv[1]
target = sys.argv[2]
parts = urlsplit(url)
query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "target"]
query.insert(0, ("target", target))
print(urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)))
PY
  )"
  backend="$(python3 - "${final_url}" <<'PY'
from urllib.parse import urlsplit
import sys
parts = urlsplit(sys.argv[1])
print(f"{parts.scheme}://{parts.netloc}")
PY
  )"
else
  declare -a query_parts=()
  query_parts+=("target=$(urlencode "${target}")")
  query_parts+=("url=$(urlencode "${source_url}")")

  if [[ -n "${config_url}" ]]; then
    query_parts+=("config=$(urlencode "${config_url}")")
  fi

  for kv in "${extra_params[@]}"; do
    if [[ "${kv}" != *=* ]]; then
      echo "Error: extra parameter must be k=v, got: ${kv}" >&2
      exit 1
    fi
    k="${kv%%=*}"
    v="${kv#*=}"
    query_parts+=("$(urlencode "${k}")=$(urlencode "${v}")")
  done

  query=""
  for part in "${query_parts[@]}"; do
    if [[ -z "${query}" ]]; then
      query="${part}"
    else
      query+="&${part}"
    fi
  done

  final_url="${backend%/}/sub?${query}"
fi
tmp_file="$(mktemp)"
trap 'rm -f "${tmp_file}"' EXIT

echo "---------------------------------------------------"
echo "subconverter backend: ${backend}"
echo "target: ${target}"
echo "output path: ${output_path}"
echo "---------------------------------------------------"

if ! curl -fL --retry 2 --connect-timeout 10 -o "${tmp_file}" "${final_url}"; then
  echo "Error: failed to download converted sing-box config" >&2
  exit 1
fi

if ! python3 -m json.tool "${tmp_file}" >/dev/null 2>&1; then
  echo "Error: backend response is not valid JSON. Check backend URL and target=singbox support." >&2
  exit 1
fi

mkdir -p "$(dirname "${output_path}")"
install -m 0600 "${tmp_file}" "${output_path}"

echo "Done. sing-box config saved: ${output_path}"
echo "Next check manually: ./sing_box/sing-box check -c ${output_path}"
