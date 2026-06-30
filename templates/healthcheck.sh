#!/usr/bin/env bash
set -uo pipefail

SERVICE_NAME="${SERVICE_NAME:-mihomo}"
TUN_DEV="${TUN_DEV:-Meta}"
PROXY_ADDR="${PROXY_ADDR:-}"
PROBE_URL="${PROBE_URL:-http://connectivitycheck.gstatic.com/generate_204}"
PROBE_ATTEMPTS="${PROBE_ATTEMPTS:-3}"
PROBE_TIMEOUT="${PROBE_TIMEOUT:-8}"
PROBE_GAP="${PROBE_GAP:-4}"
MIN_UPTIME="${MIN_UPTIME:-90}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

if [[ -z "${PROXY_ADDR}" ]]; then
  runtime_config="/etc/mihomo/${SERVICE_NAME}.yaml"
  if [[ -r "${runtime_config}" ]] && command -v python3 >/dev/null 2>&1; then
    PROXY_ADDR="$(python3 - "${runtime_config}" <<'PY' 2>/dev/null || true
import re, sys
text = open(sys.argv[1], encoding="utf-8").read().splitlines()
for key in ("mixed-port", "port"):
    for line in text:
        m = re.match(rf"^{re.escape(key)}\s*:\s*([0-9]+)\s*$", line)
        if m:
            print("127.0.0.1:" + m.group(1))
            raise SystemExit
PY
)"
  fi
fi
PROXY_ADDR="${PROXY_ADDR:-127.0.0.1:7890}"

have_uplink() {
  local dev
  while read -r dev; do
    [[ -n "${dev}" && "${dev}" != "${TUN_DEV}" ]] && return 0
  done < <(ip route show default 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="dev") print $(i+1)}')
  return 1
}

proxy_works() {
  local i
  for ((i = 1; i <= PROBE_ATTEMPTS; i++)); do
    if curl -fsS -o /dev/null -m "${PROBE_TIMEOUT}" -x "http://${PROXY_ADDR}" "${PROBE_URL}"; then
      return 0
    fi
    [[ ${i} -lt ${PROBE_ATTEMPTS} ]] && sleep "${PROBE_GAP}"
  done
  return 1
}

service_uptime_seconds() {
  local enter enter_s now_s
  enter="$(systemctl show -p ActiveEnterTimestamp --value "${SERVICE_NAME}" 2>/dev/null)"
  [[ -z "${enter}" ]] && { echo 999999; return; }
  enter_s="$(date -d "${enter}" +%s 2>/dev/null || echo 0)"
  now_s="$(date +%s)"
  echo $(( now_s - enter_s ))
}

main() {
  if ! systemctl is-active --quiet "${SERVICE_NAME}"; then
    log "${SERVICE_NAME} is not active; leaving it to systemd."
    return 0
  fi
  if ! have_uplink; then
    log "No uplink (only ${TUN_DEV}/none); skipping."
    return 0
  fi
  if proxy_works; then
    return 0
  fi
  local uptime
  uptime="$(service_uptime_seconds)"
  if [[ "${uptime}" -lt "${MIN_UPTIME}" ]]; then
    log "Proxy probe failed but ${SERVICE_NAME} is only ${uptime}s old; letting it settle."
    return 0
  fi
  log "Uplink present but proxy ${PROXY_ADDR} dead; restarting ${SERVICE_NAME}."
  systemctl restart "${SERVICE_NAME}"
}

main "$@"

