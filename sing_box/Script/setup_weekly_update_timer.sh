#!/usr/bin/env bash

# Install a systemd timer that runs update_and_redeploy.sh every Monday:
# it refreshes the sing-box core, Web UI, and CN rule sets, then reinstalls
# and restarts the sing-box service.

set -euo pipefail

TIMER_NAME="sing-box-update"
ONCALENDAR="Mon *-*-* 03:00:00"
RANDOM_DELAY="30min"
ACTION="install"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPDATE_SCRIPT="${SCRIPT_DIR}/update_and_redeploy.sh"

usage() {
  cat <<'EOF'
Usage:
  sudo ./sing_box/Script/setup_weekly_update_timer.sh [options]
  sudo ./sing_box/Script/setup_weekly_update_timer.sh --remove [options]

Options:
  -n, --name <name>        Timer/service base name, default: sing-box-update
      --on-calendar <expr> systemd OnCalendar expression,
                           default: "Mon *-*-* 03:00:00" (every Monday 03:00)
      --delay <duration>   RandomizedDelaySec to spread GitHub load,
                           default: 30min
      --remove             Stop, disable, and remove the timer and service
  -h, --help               Show help

Examples:
  sudo ./sing_box/Script/setup_weekly_update_timer.sh
  sudo ./sing_box/Script/setup_weekly_update_timer.sh --on-calendar "Mon *-*-* 04:30:00"
  sudo ./sing_box/Script/setup_weekly_update_timer.sh --remove
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--name)
      TIMER_NAME="${2:-}"
      shift 2
      ;;
    --on-calendar)
      ONCALENDAR="${2:-}"
      shift 2
      ;;
    --delay)
      RANDOM_DELAY="${2:-}"
      shift 2
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
  echo "Error: please run as root, for example: sudo ./sing_box/Script/setup_weekly_update_timer.sh" >&2
  exit 1
fi

if [[ -z "${TIMER_NAME}" ]]; then
  echo "Error: timer name cannot be empty" >&2
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "Error: systemctl is required" >&2
  exit 1
fi

SERVICE_FILE="/etc/systemd/system/${TIMER_NAME}.service"
TIMER_FILE="/etc/systemd/system/${TIMER_NAME}.timer"

remove_timer() {
  systemctl stop "${TIMER_NAME}.timer" >/dev/null 2>&1 || true
  systemctl disable "${TIMER_NAME}.timer" >/dev/null 2>&1 || true
  systemctl stop "${TIMER_NAME}.service" >/dev/null 2>&1 || true

  local removed="no"
  if [[ -f "${TIMER_FILE}" ]]; then
    rm -f "${TIMER_FILE}"
    echo "Removed timer file: ${TIMER_FILE}"
    removed="yes"
  fi
  if [[ -f "${SERVICE_FILE}" ]]; then
    rm -f "${SERVICE_FILE}"
    echo "Removed service file: ${SERVICE_FILE}"
    removed="yes"
  fi
  if [[ "${removed}" == "no" ]]; then
    echo "No timer/service files found for: ${TIMER_NAME}"
  fi

  systemctl daemon-reload
  systemctl reset-failed "${TIMER_NAME}.service" >/dev/null 2>&1 || true
  systemctl reset-failed "${TIMER_NAME}.timer" >/dev/null 2>&1 || true
  echo "Timer removed: ${TIMER_NAME}.timer"
}

if [[ "${ACTION}" == "remove" ]]; then
  remove_timer
  exit 0
fi

if [[ ! -x "${UPDATE_SCRIPT}" ]]; then
  echo "Error: update script not found or not executable: ${UPDATE_SCRIPT}" >&2
  echo "Hint: chmod +x ${UPDATE_SCRIPT}" >&2
  exit 1
fi

cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=Weekly sing-box core, UI, and rule-set update (${TIMER_NAME})
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=${UPDATE_SCRIPT}
EOF

echo "Wrote service file: ${SERVICE_FILE}"

cat > "${TIMER_FILE}" <<EOF
[Unit]
Description=Run ${TIMER_NAME}.service weekly on Monday

[Timer]
OnCalendar=${ONCALENDAR}
RandomizedDelaySec=${RANDOM_DELAY}
Persistent=true
Unit=${TIMER_NAME}.service

[Install]
WantedBy=timers.target
EOF

echo "Wrote timer file: ${TIMER_FILE}"

systemctl daemon-reload
systemctl enable --now "${TIMER_NAME}.timer"

echo "Timer enabled: ${TIMER_NAME}.timer"
echo ""
echo "Next scheduled run:"
systemctl list-timers --no-pager "${TIMER_NAME}.timer" | sed -n '1,3p'
echo ""
echo "Run once now to verify:    sudo systemctl start ${TIMER_NAME}.service"
echo "Follow logs:               journalctl -u ${TIMER_NAME}.service -f"
