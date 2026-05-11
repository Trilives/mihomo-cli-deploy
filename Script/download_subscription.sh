#!/usr/bin/env bash

set -euo pipefail

source_url=""
filename=""

usage() {
  cat <<'EOF'
用法:
  ./download_subscription.sh -u <订阅链接> [选项]

选项:
  -u, --url <url>       订阅链接(必填)
  -f, --filename <name>  保存文件名(默认: config.yaml)
  -h, --help            显示帮助

示例:
  ./download_subscription.sh -u 'https://example.com/sub?token=abc'
  ./download_subscription.sh -u 'https://example.com/sub?token=abc' -f 'my-config.yaml'
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -u|--url)
      source_url="${2:-}"
      shift 2
      ;;
    -f|--filename)
      filename="${2:-}"
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
  echo "错误: 缺少订阅链接，请使用 -u 或 --url" >&2
  usage
  exit 1
fi

PARENT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -z "$filename" ]]; then
  output_name="config.yaml"
else
  output_name="$filename"
fi

output_path="${PARENT_DIR}/${output_name}"

echo "---------------------------------------------------"
echo "订阅链接: $source_url"
echo "目标保存路径: $output_path"
echo "---------------------------------------------------"

echo "正在请求订阅文件..."

if curl -L -f -s -o "$output_path" "$source_url"; then
  echo "成功！文件已保存。"
  echo "文件信息: $(ls -lh "$output_path")"
else
  echo "错误: 下载失败，请检查网络或订阅链接是否有效。" >&2
  exit 1
fi
