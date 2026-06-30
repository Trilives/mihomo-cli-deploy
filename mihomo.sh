#!/usr/bin/env bash
# Mihomo 部署系统 · 瘦入口
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

err() { printf '\033[31m[错误]\033[0m %s\n' "$*" >&2; }
info() { printf '\033[36m[信息]\033[0m %s\n' "$*"; }

missing=()
for cmd in python3 curl tar; do
  command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
done

if [ "${#missing[@]}" -ne 0 ]; then
  err "缺少必要命令: ${missing[*]}"
  if printf '%s\n' "${missing[@]}" | grep -qx python3; then
    info "Debian/Ubuntu: sudo apt update && sudo apt install -y python3"
    info "Fedora/RHEL:   sudo dnf install -y python3"
    info "Arch:          sudo pacman -S python"
  fi
  exit 1
fi

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  err "需要 python3 >= 3.10，当前 $(python3 -V 2>&1)"
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  info "未检测到 systemctl：可生成配置，但注册系统服务需要 systemd。"
fi

export PYTHONPATH="$ROOT/lib${PYTHONPATH:+:$PYTHONPATH}"
export MIHOMO_DEPLOY_ROOT="$ROOT"
exec python3 -m mihomo_deploy "$@"
