#!/usr/bin/env bash

set -euo pipefail

SERVICE_NAME="sing-box"
CONFLICTING_SERVICE_NAME="mihomo"
RUN_USER="root"
AUTO_START="yes"
ACTION="install"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SING_BOX_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BIN_PATH="${SING_BOX_DIR}/sing-box"
CONFIG_PATH="${SING_BOX_DIR}/config.json"
RUNTIME_DIR="/etc/sing-box"

usage() {
  cat <<'EOF'
Usage:
  sudo ./sing_box/Script/setup_sing_box_service.sh [options]
  sudo ./sing_box/Script/setup_sing_box_service.sh --remove [options]

Options:
  -n, --name <service>     Service name, default: sing-box
  -b, --bin <path>         Source sing-box executable, default: sing_box/sing-box
  -c, --config <path>      Source sing-box config, default: sing_box/config.json
  -d, --runtime-dir <path> Runtime directory the service runs from,
                           default: /etc/sing-box
  -u, --user <name>        Run user, default: root
      --no-start           Enable service but do not start immediately
      --remove             Stop, disable, and remove the systemd service
  -h, --help               Show help

The runtime directory is a self-contained copy of everything the service needs
(binary, config, ruleset/, ui/, cache). Staging it outside the source tree keeps
the service independent of the repository path and avoids permission problems
when the source lives under /home.

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
    -d|--runtime-dir|--workdir)
      RUNTIME_DIR="${2:-}"
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

if [[ -z "${RUNTIME_DIR}" ]]; then
  echo "Error: runtime directory cannot be empty" >&2
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "Error: systemctl is required" >&2
  exit 1
fi

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
RUNTIME_BIN_PATH="${RUNTIME_DIR}/sing-box"
RUNTIME_CONFIG_PATH="${RUNTIME_DIR}/${SERVICE_NAME}.json"
RUNTIME_CACHE_PATH="${RUNTIME_DIR}/${SERVICE_NAME}.cache.db"
RUNTIME_RULESET_DIR="${RUNTIME_DIR}/ruleset"
RUNTIME_UI_DIR="${RUNTIME_DIR}/ui"

remove_service_by_name() {
  local service_name="$1"
  local service_file="/etc/systemd/system/${service_name}.service"

  if systemctl list-unit-files "${service_name}.service" >/dev/null 2>&1; then
    systemctl stop "${service_name}.service" >/dev/null 2>&1 || true
    systemctl disable "${service_name}.service" >/dev/null 2>&1 || true
  fi

  if [[ -f "${service_file}" ]]; then
    rm -f "${service_file}"
    echo "Removed service file: ${service_file}"
  else
    echo "Service file not found: ${service_file}"
  fi

  systemctl daemon-reload
  systemctl reset-failed "${service_name}.service" >/dev/null 2>&1 || true
  echo "Service removed: ${service_name}.service"
}

remove_service() {
  remove_service_by_name "${SERVICE_NAME}"
}

# Clean up the staged runtime files for this service. Drop the whole runtime
# directory only when no other managed service config remains there.
remove_runtime() {
  if [[ ! -d "${RUNTIME_DIR}" ]]; then
    return 0
  fi
  rm -f "${RUNTIME_CONFIG_PATH}" "${RUNTIME_CACHE_PATH}"
  if find "${RUNTIME_DIR}" -maxdepth 1 -name '*.json' -print -quit | grep -q .; then
    echo "Removed runtime config: ${RUNTIME_CONFIG_PATH} (kept shared files for other services)"
  else
    rm -rf "${RUNTIME_DIR}"
    echo "Removed runtime directory: ${RUNTIME_DIR}"
  fi
}

if [[ "${ACTION}" == "remove" ]]; then
  remove_service
  remove_runtime
  exit 0
fi

if [[ ! -x "${BIN_PATH}" ]]; then
  echo "Error: sing-box executable not found or not executable: ${BIN_PATH}" >&2
  echo "Hint: run ./sing_box/Script/update_sing_box_core.sh first" >&2
  exit 1
fi

if [[ ! -f "${CONFIG_PATH}" ]]; then
  echo "Error: config file not found: ${CONFIG_PATH}" >&2
  exit 1
fi

BIN_PATH="$(realpath "${BIN_PATH}")"
CONFIG_PATH="$(realpath "${CONFIG_PATH}")"

# The config references ruleset/ and ui via relative paths, resolved against the
# working directory. They live next to the source config.
SOURCE_DIR="$(dirname "${CONFIG_PATH}")"
RULESET_SRC="${SOURCE_DIR}/ruleset"
UI_SRC="${SOURCE_DIR}/ui"

if [[ ! -d "${RULESET_SRC}" ]] || [[ -z "$(find "${RULESET_SRC}" -maxdepth 1 -name '*.srs' -print -quit)" ]]; then
  echo "Error: rule sets not found in ${RULESET_SRC}" >&2
  echo "Hint: run ./sing_box/Script/update_sing_box_core.sh to download geosite-cn.srs and geoip-cn.srs" >&2
  exit 1
fi

if ! id "${RUN_USER}" >/dev/null 2>&1; then
  echo "Error: run user does not exist: ${RUN_USER}" >&2
  exit 1
fi

echo "Staging runtime files into: ${RUNTIME_DIR}"
mkdir -p "${RUNTIME_DIR}"
chmod 0755 "${RUNTIME_DIR}"

# Install via a temp name + atomic rename so replacing the binary while the
# service is still running does not fail with ETXTBSY.
install -o root -g root -m 0755 "${BIN_PATH}" "${RUNTIME_BIN_PATH}.new"
mv -f "${RUNTIME_BIN_PATH}.new" "${RUNTIME_BIN_PATH}"
echo "Installed binary: ${RUNTIME_BIN_PATH}"

install -o root -g root -m 0644 "${CONFIG_PATH}" "${RUNTIME_CONFIG_PATH}"
echo "Installed config: ${RUNTIME_CONFIG_PATH}"

rm -rf "${RUNTIME_RULESET_DIR}"
mkdir -p "${RUNTIME_RULESET_DIR}"
chmod 0755 "${RUNTIME_RULESET_DIR}"
find "${RULESET_SRC}" -maxdepth 1 -name '*.srs' -exec install -o root -g root -m 0644 {} "${RUNTIME_RULESET_DIR}/" \;
echo "Installed rule sets: ${RUNTIME_RULESET_DIR}"

if [[ -d "${UI_SRC}" ]]; then
  rm -rf "${RUNTIME_UI_DIR}"
  mkdir -p "${RUNTIME_UI_DIR}"
  cp -a "${UI_SRC}/." "${RUNTIME_UI_DIR}/"
  chown -R root:root "${RUNTIME_UI_DIR}"
  echo "Installed Web UI: ${RUNTIME_UI_DIR}"
else
  echo "Warning: Web UI not found at ${UI_SRC}; clash_api external_ui will be unavailable until you run update_sing_box_core.sh"
fi

# Rewrite the runtime config so every path is absolute and points inside the
# runtime directory. This decouples the service from the working directory and
# from whatever relative convention the generator used (ruleset/ vs
# sing_box/ruleset/), and lets a non-root run user write the cache file.
python3 - <<PY
import json
from pathlib import Path

config_path = Path("${RUNTIME_CONFIG_PATH}")
cache_path = Path("${RUNTIME_CACHE_PATH}")
ruleset_dir = Path("${RUNTIME_RULESET_DIR}")
ui_dir = Path("${RUNTIME_UI_DIR}")

data = json.loads(config_path.read_text(encoding="utf-8"))

experimental = data.get("experimental") or {}
cache_file = experimental.get("cache_file") or {}
cache_file["enabled"] = True
cache_file["path"] = str(cache_path)
experimental["cache_file"] = cache_file

clash_api = experimental.get("clash_api")
if isinstance(clash_api, dict) and clash_api.get("external_ui"):
    clash_api["external_ui"] = str(ui_dir)
data["experimental"] = experimental

route = data.get("route")
if isinstance(route, dict):
    for rule_set in route.get("rule_set") or []:
        if isinstance(rule_set, dict) and rule_set.get("type") == "local" and rule_set.get("path"):
            rule_set["path"] = str(ruleset_dir / Path(rule_set["path"]).name)

config_path.write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

if [[ "${RUN_USER}" == "root" ]]; then
  install -o root -g root -m 0644 /dev/null "${RUNTIME_CACHE_PATH}"
else
  install -o "${RUN_USER}" -g "${RUN_USER}" -m 0644 /dev/null "${RUNTIME_CACHE_PATH}"
fi
echo "Prepared cache file: ${RUNTIME_CACHE_PATH}"

# Verify the run user can actually use the staged runtime before we wire up the
# service. Everything lives under a root-owned, world-readable system directory.
check_run_user_access() {
  local test_expr="$1"
  local path="$2"
  local description="$3"

  if ! runuser -u "${RUN_USER}" -- test "${test_expr}" "${path}"; then
    echo "Error: ${description} is not accessible by service user '${RUN_USER}': ${path}" >&2
    exit 1
  fi
}

check_run_user_access -x "${RUNTIME_BIN_PATH}" "staged sing-box executable"
check_run_user_access -r "${RUNTIME_CONFIG_PATH}" "staged sing-box config"
check_run_user_access -x "${RUNTIME_DIR}" "runtime directory"

# Re-validate the staged config from the runtime directory.
( cd "${RUNTIME_DIR}" && "${RUNTIME_BIN_PATH}" check -c "${RUNTIME_CONFIG_PATH}" )

echo "Removing existing service: ${SERVICE_NAME}.service"
remove_service

if [[ "${SERVICE_NAME}" != "${CONFLICTING_SERVICE_NAME}" ]]; then
  echo "Removing conflicting service: ${CONFLICTING_SERVICE_NAME}.service"
  remove_service_by_name "${CONFLICTING_SERVICE_NAME}"
fi

cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=sing-box Service (${SERVICE_NAME})
Documentation=https://sing-box.sagernet.org/
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${RUNTIME_DIR}
ExecStart=${RUNTIME_BIN_PATH} run -c ${RUNTIME_CONFIG_PATH}
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
