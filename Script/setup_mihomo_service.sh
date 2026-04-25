#!/usr/bin/env bash

set -euo pipefail

SERVICE_NAME="mihomo"
RUN_USER="root"
AUTO_START="yes"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BIN_PATH="$BASE_DIR/mihomo"
WORK_DIR="$BASE_DIR"

usage() {
  cat <<'EOF'
用法:
  sudo ./Script/setup_mihomo_service.sh [选项]

选项:
  -n, --name <service>    服务名，默认 mihomo
  -b, --bin <path>        mihomo 可执行文件路径，默认 ../mihomo
  -d, --workdir <path>    工作目录（含 config.yaml），默认脚本上级目录
  -u, --user <name>       运行用户，默认 root
      --no-start          仅 enable，不立即启动
  -h, --help              显示帮助

示例:
  sudo ./Script/setup_mihomo_service.sh
  sudo ./Script/setup_mihomo_service.sh -n mihomo-main --no-start
  sudo ./Script/setup_mihomo_service.sh -b /opt/mihomo/mihomo -d /opt/mihomo
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--name)
      SERVICE_NAME="${2:-}"
      shift 2
      ;;
    -b|--bin)
      BIN_PATH="${2:-}"
      shift 2
      ;;
    -d|--workdir)
      WORK_DIR="${2:-}"
      shift 2
      ;;
    -u|--user)
      RUN_USER="${2:-}"
      shift 2
      ;;
    --no-start)
      AUTO_START="no"
      shift
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

if [[ $EUID -ne 0 ]]; then
  echo "错误: 请使用 root 运行（例如 sudo ./Script/setup_mihomo_service.sh）" >&2
  exit 1
fi

if [[ -z "$SERVICE_NAME" ]]; then
  echo "错误: 服务名不能为空" >&2
  exit 1
fi

if [[ ! -x "$BIN_PATH" ]]; then
  echo "错误: mihomo 可执行文件不存在或不可执行: $BIN_PATH" >&2
  exit 1
fi

if [[ ! -d "$WORK_DIR" ]]; then
  echo "错误: 工作目录不存在: $WORK_DIR" >&2
  exit 1
fi

if [[ ! -f "$WORK_DIR/config.yaml" ]]; then
  echo "错误: 未找到配置文件: $WORK_DIR/config.yaml" >&2
  exit 1
fi

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Mihomo Service (${SERVICE_NAME})
Documentation=https://wiki.metacubex.one
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${WORK_DIR}
ExecStart=${BIN_PATH} -d ${WORK_DIR}
Restart=on-failure
RestartSec=3
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF

echo "已写入服务文件: ${SERVICE_FILE}"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"

if [[ "$AUTO_START" == "yes" ]]; then
  systemctl restart "${SERVICE_NAME}.service"
  echo "服务已启动: ${SERVICE_NAME}.service"
else
  echo "已启用开机自启，未立即启动（--no-start）"
fi

echo ""
echo "当前服务状态（前 25 行）："
systemctl status --no-pager "${SERVICE_NAME}.service" | sed -n '1,25p'
