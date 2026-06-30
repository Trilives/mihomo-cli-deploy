#!/usr/bin/env bash

# One-shot uninstall: run every sing-box --remove command in sequence.
#
# Tears down everything the setup scripts installed, in reverse order of
# dependency so the watchdog / timer are gone before the service itself:
#   1. setup_resilience.sh          --remove  (NetworkManager hook + watchdog)
#   2. setup_weekly_update_timer.sh --remove  (weekly auto-update timer)
#   3. setup_sing_box_service.sh    --remove  (systemd service + runtime files)
#
# Each step is best-effort: a failure is reported but does not abort the rest,
# so a partially-installed setup still gets fully cleaned up.
#
# Note on -n: for setup_resilience.sh and setup_sing_box_service.sh, -n is the
# *service* name and is forwarded from --name here. setup_weekly_update_timer.sh's
# -n is the *timer* name (default sing-box-update, independent of the service),
# so this script does not forward --name to it; override with --timer-name.

set -uo pipefail

SERVICE_NAME="sing-box"
TIMER_NAME="sing-box-update"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
Usage:
  sudo ./sing_box/Script/uninstall_all_singbox.sh [options]

Runs every sing-box uninstall command in sequence:
  1. setup_resilience.sh          --remove
  2. setup_weekly_update_timer.sh --remove
  3. setup_sing_box_service.sh    --remove

Options:
  -n, --name <service>     sing-box service name, default: sing-box
      --timer-name <name>  weekly-update timer name, default: sing-box-update
  -h, --help               Show help

Examples:
  sudo ./sing_box/Script/uninstall_all_singbox.sh
  sudo ./sing_box/Script/uninstall_all_singbox.sh -n sing-box-main
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--name)      SERVICE_NAME="${2:-}"; shift 2 ;;
    --timer-name)   TIMER_NAME="${2:-}"; shift 2 ;;
    -h|--help)      usage; exit 0 ;;
    *)
      echo "Error: unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ ${EUID} -ne 0 ]]; then
  echo "Error: please run as root, for example: sudo ./sing_box/Script/uninstall_all_singbox.sh" >&2
  exit 1
fi

if [[ -z "${SERVICE_NAME}" ]]; then
  echo "Error: service name cannot be empty" >&2
  exit 1
fi

if [[ -z "${TIMER_NAME}" ]]; then
  echo "Error: timer name cannot be empty" >&2
  exit 1
fi

failures=0

# run_remove <script> [extra args...]
run_remove() {
  local script="$1"; shift
  local path="${SCRIPT_DIR}/${script}"

  echo
  echo "==> ${script} --remove $*"
  if [[ ! -f "${path}" ]]; then
    echo "!! ${script} not found at ${path} (skipping)"
    failures=$((failures + 1))
    return
  fi
  bash "${path}" --remove "$@" || { echo "!! ${script} failed (continuing)"; failures=$((failures + 1)); }
}

run_remove "setup_resilience.sh" -n "${SERVICE_NAME}"
run_remove "setup_weekly_update_timer.sh" -n "${TIMER_NAME}"
run_remove "setup_sing_box_service.sh" -n "${SERVICE_NAME}"

echo
if [[ "${failures}" -eq 0 ]]; then
  echo "All uninstall steps completed for: ${SERVICE_NAME}"
else
  echo "Uninstall finished with ${failures} failed/skipped step(s) for: ${SERVICE_NAME}" >&2
  exit 1
fi
