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
SYSTEM_CONFIG_DIR="/etc/sing-box"
SYSTEM_CONFIG_PATH="${SYSTEM_CONFIG_DIR}/${SERVICE_NAME}.json"
SYSTEM_CACHE_PATH="${SYSTEM_CONFIG_DIR}/${SERVICE_NAME}.cache.db"

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

BIN_PATH="$(realpath "${BIN_PATH}")"
CONFIG_PATH="$(realpath "${CONFIG_PATH}")"
WORK_DIR="$(realpath "${WORK_DIR}")"

if ! id "${RUN_USER}" >/dev/null 2>&1; then
  echo "Error: run user does not exist: ${RUN_USER}" >&2
  exit 1
fi

check_run_user_access() {
  local test_expr="$1"
  local path="$2"
  local description="$3"
  local current_user="${SUDO_USER:-$(id -un)}"

  if ! runuser -u "${RUN_USER}" -- test "${test_expr}" "${path}"; then
    cat >&2 <<EOF
Error: ${description} is not accessible by service user '${RUN_USER}': ${path}

Hint:
  - Use the default root user for TUN mode, or pass '-u ${current_user}' if you want to run as your current user.
  - If the config is under /home, every parent directory must be executable by '${RUN_USER}'.
EOF
    exit 1
  fi
}

check_run_user_access -x "${BIN_PATH}" "sing-box executable"
check_run_user_access -r "${CONFIG_PATH}" "sing-box config"
check_run_user_access -x "${WORK_DIR}" "working directory"

"${BIN_PATH}" check -c "${CONFIG_PATH}"

mkdir -p "${SYSTEM_CONFIG_DIR}"
install -o root -g root -m 0644 "${CONFIG_PATH}" "${SYSTEM_CONFIG_PATH}"
echo "Installed runtime config: ${SYSTEM_CONFIG_PATH}"

python3 - <<PY
import json
from pathlib import Path

config_path = Path("${SYSTEM_CONFIG_PATH}")
cache_path = Path("${SYSTEM_CACHE_PATH}")

data = json.loads(config_path.read_text(encoding="utf-8"))
experimental = data.get("experimental") or {}
cache_file = experimental.get("cache_file") or {}
cache_file["enabled"] = True
cache_file["path"] = str(cache_path)
experimental["cache_file"] = cache_file
data["experimental"] = experimental

config_path.write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

if [[ "${RUN_USER}" == "root" ]]; then
  install -o root -g root -m 0644 /dev/null "${SYSTEM_CACHE_PATH}"
else
  install -o "${RUN_USER}" -g "${RUN_USER}" -m 0644 /dev/null "${SYSTEM_CACHE_PATH}"
fi
echo "Prepared cache file: ${SYSTEM_CACHE_PATH}"

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
ExecStart=${BIN_PATH} run -c ${SYSTEM_CONFIG_PATH}
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
