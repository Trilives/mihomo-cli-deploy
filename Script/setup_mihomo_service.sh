#!/usr/bin/env bash

set -euo pipefail

SERVICE_NAME="mihomo"
CONFLICTING_SERVICE_NAME="sing-box"
RUN_USER="root"
AUTO_START="yes"
ACTION="install"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BIN_PATH="${BASE_DIR}/mihomo"
CONFIG_PATH="${BASE_DIR}/config.yaml"
RUNTIME_DIR="/etc/mihomo"

usage() {
  cat <<'EOF'
用法:
  sudo ./Script/setup_mihomo_service.sh [选项]
  sudo ./Script/setup_mihomo_service.sh --remove [选项]

选项:
  -n, --name <service>     服务名，默认 mihomo
  -b, --bin <path>         mihomo 源可执行文件，默认 ../mihomo
  -c, --config <path>      mihomo 源配置文件，默认 ../config.yaml
  -d, --runtime-dir <path> 服务实际运行目录，默认 /etc/mihomo
  -u, --user <name>        运行用户，默认 root
      --no-start           仅 enable，不立即启动
      --remove             停止、禁用并删除 systemd 服务，并清理暂存的运行时文件
  -h, --help               显示帮助

运行时目录是一份自包含副本（二进制、config、country.mmdb、geoip.metadb、ui/、
cache）。把它暂存到源码树之外，可让服务独立于仓库路径，并避免源码位于 /home
时的权限问题。--remove 会清理本服务的暂存配置；当目录中已无其它受管服务时，
连同共享文件一并删除。

示例:
  sudo ./Script/setup_mihomo_service.sh
  sudo ./Script/setup_mihomo_service.sh -n mihomo-main --no-start
  sudo ./Script/setup_mihomo_service.sh --remove
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
      echo "错误: 未知参数 '$1'" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ ${EUID} -ne 0 ]]; then
  echo "错误: 请使用 root 运行（例如 sudo ./Script/setup_mihomo_service.sh）" >&2
  exit 1
fi

if [[ -z "${SERVICE_NAME}" ]]; then
  echo "错误: 服务名不能为空" >&2
  exit 1
fi

if [[ -z "${RUNTIME_DIR}" ]]; then
  echo "错误: 运行时目录不能为空" >&2
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "错误: 需要 systemctl" >&2
  exit 1
fi

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
RUNTIME_CONFIG_PATH="${RUNTIME_DIR}/${SERVICE_NAME}.yaml"

ENV_FILE="${BASE_DIR}/.env"
env_value() {
  local key_regex="$1"
  [[ -f "${ENV_FILE}" ]] || return 0
  sed -nE "s/^[[:space:]]*(${key_regex})[[:space:]]*=[[:space:]]*\"?([^\"[:space:]]+)\"?.*$/\\2/p" "${ENV_FILE}" | head -n1
}

# Whether to expose the proxy ports to the LAN (allow-lan). The dashboard itself
# always stays bound to its local controller address; this only controls whether
# other devices on the LAN can use this machine as a proxy. Priority: ALLOW_LAN
# env var, then an ALLOW_LAN entry in <root>/.env. Default: false (local only).
ALLOW_LAN_RAW="${ALLOW_LAN:-$(env_value 'ALLOW_LAN')}"
case "${ALLOW_LAN_RAW,,}" in
  1|true|yes|on) ALLOW_LAN="true" ;;
  *) ALLOW_LAN="false" ;;
esac

remove_service_by_name() {
  local service_name="$1"
  local service_file="/etc/systemd/system/${service_name}.service"

  if systemctl list-unit-files "${service_name}.service" >/dev/null 2>&1; then
    systemctl stop "${service_name}.service" >/dev/null 2>&1 || true
    systemctl disable "${service_name}.service" >/dev/null 2>&1 || true
  fi

  if [[ -f "${service_file}" ]]; then
    rm -f "${service_file}"
    echo "已删除服务文件: ${service_file}"
  else
    echo "服务文件不存在: ${service_file}"
  fi

  systemctl daemon-reload
  systemctl reset-failed "${service_name}.service" >/dev/null 2>&1 || true
  echo "服务已删除: ${service_name}.service"
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
  rm -f "${RUNTIME_CONFIG_PATH}"
  if find "${RUNTIME_DIR}" -maxdepth 1 -name '*.yaml' -print -quit | grep -q .; then
    echo "已删除本服务运行时配置: ${RUNTIME_CONFIG_PATH}（保留共享文件，仍有其它服务在用）"
  else
    rm -rf "${RUNTIME_DIR}"
    echo "已删除运行时目录: ${RUNTIME_DIR}"
  fi
}

if [[ "${ACTION}" == "remove" ]]; then
  remove_service
  remove_runtime
  exit 0
fi

if [[ ! -x "${BIN_PATH}" ]]; then
  echo "错误: mihomo 可执行文件不存在或不可执行: ${BIN_PATH}" >&2
  echo "提示: 先运行 ./Script/update_core_assets.sh" >&2
  exit 1
fi

if [[ ! -f "${CONFIG_PATH}" ]]; then
  echo "错误: 未找到配置文件: ${CONFIG_PATH}" >&2
  exit 1
fi

BIN_PATH="$(realpath "${BIN_PATH}")"
CONFIG_PATH="$(realpath "${CONFIG_PATH}")"
SOURCE_DIR="$(dirname "${CONFIG_PATH}")"

if ! id "${RUN_USER}" >/dev/null 2>&1; then
  echo "错误: 运行用户不存在: ${RUN_USER}" >&2
  exit 1
fi

# Ensure the dashboard works (external-controller / external-ui / secret) and set
# allow-lan to the configured value (ALLOW_LAN, default false). The controller is
# preserved if already set and only stays/becomes a local address by default;
# allow-lan only controls whether the proxy is reachable from the LAN. Editing the
# source config keeps the generated secret across redeploys.
ensure_dashboard_settings() {
  local config_path="$1"
  local dashboard_helper="${SCRIPT_DIR}/Enhance/enable_tun_lan_dashboard.py"

  if [[ ! -x "${dashboard_helper}" ]]; then
    echo "错误: 找不到可执行的 dashboard 辅助脚本: ${dashboard_helper}" >&2
    exit 1
  fi

  if grep -Eq "^allow-lan:[[:space:]]*${ALLOW_LAN}([[:space:]]*#.*)?\$" "${config_path}" \
    && grep -Eq '^external-controller:[[:space:]]*' "${config_path}" \
    && grep -Eq '^external-ui:[[:space:]]*' "${config_path}"; then
    return 0
  fi

  echo "检测到 dashboard 配置不完整或 allow-lan 与期望值(${ALLOW_LAN})不一致，自动补全面板设置"
  python3 "${dashboard_helper}" "${config_path}" --dashboard-only --generate-secret --allow-lan "${ALLOW_LAN}"
}

ensure_dashboard_settings "${CONFIG_PATH}"

RUNTIME_BIN_PATH="${RUNTIME_DIR}/mihomo"
RUNTIME_UI_DIR="${RUNTIME_DIR}/ui"

echo "暂存运行时文件到: ${RUNTIME_DIR}"
mkdir -p "${RUNTIME_DIR}"
chmod 0755 "${RUNTIME_DIR}"

# Install via a temp name + atomic rename so replacing the binary while the
# service is still running does not fail with ETXTBSY.
install -o root -g root -m 0755 "${BIN_PATH}" "${RUNTIME_BIN_PATH}.new"
mv -f "${RUNTIME_BIN_PATH}.new" "${RUNTIME_BIN_PATH}"
echo "已安装二进制: ${RUNTIME_BIN_PATH}"

install -o root -g root -m 0644 "${CONFIG_PATH}" "${RUNTIME_CONFIG_PATH}"
echo "已安装配置: ${RUNTIME_CONFIG_PATH}"

# Geo databases: stage when present; mihomo -t below will catch a config that
# genuinely needs a missing one.
for geo in country.mmdb geoip.metadb; do
  if [[ -f "${SOURCE_DIR}/${geo}" ]]; then
    install -o root -g root -m 0644 "${SOURCE_DIR}/${geo}" "${RUNTIME_DIR}/${geo}"
    echo "已安装 geo 数据: ${RUNTIME_DIR}/${geo}"
  else
    echo "警告: 未找到 ${SOURCE_DIR}/${geo}；如配置需要请先运行 ./Script/update_core_assets.sh"
  fi
done

if [[ -d "${SOURCE_DIR}/ui" ]]; then
  rm -rf "${RUNTIME_UI_DIR}"
  mkdir -p "${RUNTIME_UI_DIR}"
  cp -a "${SOURCE_DIR}/ui/." "${RUNTIME_UI_DIR}/"
  chown -R root:root "${RUNTIME_UI_DIR}"
  echo "已安装 Web UI: ${RUNTIME_UI_DIR}"
else
  echo "警告: 未找到 ${SOURCE_DIR}/ui；面板将不可用，直到运行 ./Script/update_core_assets.sh"
fi

# When running as a non-root user, mihomo needs to write cache.db and refresh
# geo data inside its home dir, so hand ownership of the runtime dir over.
if [[ "${RUN_USER}" != "root" ]]; then
  chown -R "${RUN_USER}:${RUN_USER}" "${RUNTIME_DIR}"
  echo "已将运行时目录归属交给用户: ${RUN_USER}"
fi

check_run_user_access() {
  local test_expr="$1"
  local path="$2"
  local description="$3"

  if ! runuser -u "${RUN_USER}" -- test "${test_expr}" "${path}"; then
    echo "错误: 服务用户 '${RUN_USER}' 无法访问 ${description}: ${path}" >&2
    exit 1
  fi
}

check_run_user_access -x "${RUNTIME_BIN_PATH}" "mihomo 可执行文件"
check_run_user_access -r "${RUNTIME_CONFIG_PATH}" "mihomo 配置"
check_run_user_access -x "${RUNTIME_DIR}" "运行时目录"

# Validate the staged config from the runtime directory.
"${RUNTIME_BIN_PATH}" -d "${RUNTIME_DIR}" -f "${RUNTIME_CONFIG_PATH}" -t

echo "卸载已有服务: ${SERVICE_NAME}.service"
remove_service

if [[ "${SERVICE_NAME}" != "${CONFLICTING_SERVICE_NAME}" ]]; then
  echo "卸载冲突服务: ${CONFLICTING_SERVICE_NAME}.service"
  remove_service_by_name "${CONFLICTING_SERVICE_NAME}"
fi

cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=Mihomo Service (${SERVICE_NAME})
Documentation=https://wiki.metacubex.one
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${RUNTIME_DIR}
ExecStart=${RUNTIME_BIN_PATH} -d ${RUNTIME_DIR} -f ${RUNTIME_CONFIG_PATH}
Restart=on-failure
RestartSec=3
LimitNOFILE=1048576
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_NET_RAW
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_NET_RAW

[Install]
WantedBy=multi-user.target
EOF

echo "已写入服务文件: ${SERVICE_FILE}"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"

if [[ "${AUTO_START}" == "yes" ]]; then
  systemctl restart "${SERVICE_NAME}.service"
  echo "服务已启动: ${SERVICE_NAME}.service"
else
  echo "已启用开机自启，未立即启动（--no-start）"
fi

echo ""
echo "当前服务状态（前 25 行）："
systemctl status --no-pager "${SERVICE_NAME}.service" | sed -n '1,25p'
