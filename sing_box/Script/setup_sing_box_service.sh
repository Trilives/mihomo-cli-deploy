#!/usr/bin/env bash

set -euo pipefail

SERVICE_NAME="sing-box"
RUN_USER="root"
AUTO_START="yes"
ACTION="install"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SING_BOX_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BIN_PATH="${SING_BOX_DIR}/sing-box"
CONFIG_PATH="${SING_BOX_DIR}/config.json"
WORK_DIR="${SING_BOX_DIR}"

usage() {
  cat <<'EOF'
Usage:
  sudo ./sing_box/Script/setup_sing_box_service.sh [options]
  sudo ./sing_box/Script/setup_sing_box_service.sh --remove [options]

Options:
  -n, --name <service>     Service name, default: sing-box
  -b, --bin <path>         sing-box executable path, default: sing_box/sing-box
  -c, --config <path>      sing-box config path, default: sing_box/config.json
  -d, --workdir <path>     Working directory, default: sing_box
  -u, --user <name>        Run user, default: root
      --no-start           Enable service but do not start immediately
      --remove             Stop, disable, and remove the systemd service
  -h, --help               Show help

Examples:
  sudo ./sing_box/Script/setup_sing_box_service.sh
  sudo ./sing_box/Script/setup_sing_box_service.sh --no-start
  sudo ./sing_box/Script/setup_sing_box_service.sh --remove
  sudo ./sing_box/Script/setup_sing_box_service.sh -n sing-box-main --remove
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
    -c|--config)
      CONFIG_PATH="${2:-}"
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
    --remove)
      ACTION="remove"
      shift
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

if [[ ${EUID} -ne 0 ]]; then
  echo "Error: please run as root, for example: sudo ./sing_box/Script/setup_sing_box_service.sh" >&2
  exit 1
fi

if [[ -z "${SERVICE_NAME}" ]]; then
  echo "Error: service name cannot be empty" >&2
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "Error: systemctl is required" >&2
  exit 1
fi

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

remove_service() {
  if systemctl list-unit-files "${SERVICE_NAME}.service" >/dev/null 2>&1; then
    systemctl stop "${SERVICE_NAME}.service" >/dev/null 2>&1 || true
    systemctl disable "${SERVICE_NAME}.service" >/dev/null 2>&1 || true
  fi

  if [[ -f "${SERVICE_FILE}" ]]; then
    rm -f "${SERVICE_FILE}"
    echo "Removed service file: ${SERVICE_FILE}"
  else
    echo "Service file not found: ${SERVICE_FILE}"
  fi

  systemctl daemon-reload
  systemctl reset-failed "${SERVICE_NAME}.service" >/dev/null 2>&1 || true
  echo "Service removed: ${SERVICE_NAME}.service"
}

if [[ "${ACTION}" == "remove" ]]; then
  remove_service
  exit 0
fi

if [[ ! -x "${BIN_PATH}" ]]; then
  echo "Error: sing-box executable not found or not executable: ${BIN_PATH}" >&2
  exit 1
fi

if [[ ! -f "${CONFIG_PATH}" ]]; then
  echo "Error: config file not found: ${CONFIG_PATH}" >&2
  exit 1
fi

if [[ ! -d "${WORK_DIR}" ]]; then
  echo "Error: working directory not found: ${WORK_DIR}" >&2
  exit 1
fi

"${BIN_PATH}" check -c "${CONFIG_PATH}"

cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=sing-box Service (${SERVICE_NAME})
Documentation=https://sing-box.sagernet.org/
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${WORK_DIR}
ExecStart=${BIN_PATH} run -c ${CONFIG_PATH}
Restart=on-failure
RestartSec=3
LimitNOFILE=1048576
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_NET_RAW
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_NET_RAW

[Install]
WantedBy=multi-user.target
EOF

echo "Wrote service file: ${SERVICE_FILE}"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"

if [[ "${AUTO_START}" == "yes" ]]; then
  systemctl restart "${SERVICE_NAME}.service"
  echo "Service started: ${SERVICE_NAME}.service"
else
  echo "Service enabled, not started (--no-start)"
fi

echo ""
echo "Current service status:"
systemctl status --no-pager "${SERVICE_NAME}.service" | sed -n '1,25p'
