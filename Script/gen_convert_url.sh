#!/usr/bin/env bash

set -euo pipefail

OFFICIAL_BACKEND="https://sub.fndroid.com"
MIRROR_BACKEND="https://api.v1.mk"

backend="official"
source_url=""
target="clash"
config_url=""
filename=""

declare -a extra_params=()

usage() {
  cat <<'EOF'
用法:
  ./gen_convert_url.sh -u <原始订阅链接> [选项]

选项:
  -u, --url <url>            原始订阅链接(必填)
  -b, --backend <name|url>   后端: official | mirror | 自定义URL
  -t, --target <target>      转换目标(默认: clash)
  -c, --config <url>         远程配置模板 URL(可选)
  -f, --filename <name>      下载文件名(可选)
  -p, --param <k=v>          追加自定义参数(可重复)
  -h, --help                 显示帮助

后端预设:
  official -> https://sub.fndroid.com
  mirror   -> https://api.v1.mk

示例:
  ./gen_convert_url.sh -u 'https://example.com/sub?token=abc'
  ./gen_convert_url.sh -b mirror -u 'https://example.com/sub?token=abc' -p 'emoji=true' -p 'udp=true'
  ./gen_convert_url.sh -b 'https://your-backend.example.com' -u 'https://example.com/sub?token=abc' -c 'https://raw.githubusercontent.com/xxx/rules.ini'
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

build_backend_base() {
  local input="$1"
  case "$input" in
    official) printf '%s' "$OFFICIAL_BACKEND" ;;
    mirror) printf '%s' "$MIRROR_BACKEND" ;;
    http://*|https://*) printf '%s' "$input" ;;
    *)
      echo "错误: 无效后端 '$input'，请使用 official / mirror / 自定义URL" >&2
      exit 1
      ;;
  esac
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
    -t|--target)
      target="${2:-}"
      shift 2
      ;;
    -c|--config)
      config_url="${2:-}"
      shift 2
      ;;
    -f|--filename)
      filename="${2:-}"
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
      echo "错误: 未知参数 '$1'" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$source_url" ]]; then
  echo "错误: 缺少原始订阅链接，请使用 -u 或 --url" >&2
  usage
  exit 1
fi

backend_base="$(build_backend_base "$backend")"

declare -a query_parts=()
query_parts+=("target=$(urlencode "$target")")
query_parts+=("url=$(urlencode "$source_url")")

if [[ -n "$config_url" ]]; then
  query_parts+=("config=$(urlencode "$config_url")")
fi

if [[ -n "$filename" ]]; then
  query_parts+=("filename=$(urlencode "$filename")")
fi

for kv in "${extra_params[@]}"; do
  if [[ "$kv" != *=* ]]; then
    echo "错误: 自定义参数必须是 k=v 格式，收到 '$kv'" >&2
    exit 1
  fi
  k="${kv%%=*}"
  v="${kv#*=}"
  query_parts+=("$(urlencode "$k")=$(urlencode "$v")")
done

query=""
for part in "${query_parts[@]}"; do
  if [[ -z "$query" ]]; then
    query="$part"
  else
    query+="&$part"
  fi
done

final_url="${backend_base%/}/sub?${query}"
printf '%s\n' "$final_url"
