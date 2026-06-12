#!/usr/bin/env bash
#
# test_network_exit.sh — 探测当前网络到各主流站点的「实际出口」
#
# 不同站点可能因分流规则走不同代理 / 直连，本脚本逐站请求并解析出口
# IP、所在国家/地区以及 Cloudflare 机房（colo），用于快速核对分流是否
# 符合预期，以及各家是否命中了同一出口。
#
#   - *.cdn-cgi/trace : Cloudflare 暴露的诊断端点，返回 ip / loc / colo
#   - ip.me           : 返回纯出口 IP（作为「默认线路」基准对照）
#
# 用法:
#   ./test_network_exit.sh              # 普通输出
#   ./test_network_exit.sh -4           # 强制 IPv4
#   ./test_network_exit.sh -6           # 强制 IPv6
#   PROXY=http://127.0.0.1:7890 ./test_network_exit.sh   # 经指定代理探测

set -uo pipefail

TIMEOUT="${TIMEOUT:-15}"
PROXY="${PROXY:-}"

# ---- curl 选项 -----------------------------------------------------------
CURL_OPTS=(-s --max-time "${TIMEOUT}")
[[ -n "${PROXY}" ]] && CURL_OPTS+=(--proxy "${PROXY}")
case "${1:-}" in
  -4) CURL_OPTS+=(-4) ;;
  -6) CURL_OPTS+=(-6) ;;
esac

# ---- 颜色 ----------------------------------------------------------------
if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GRN=$'\033[32m'
  YEL=$'\033[33m'; CYA=$'\033[36m'; RST=$'\033[0m'
else
  BOLD=''; DIM=''; RED=''; GRN=''; YEL=''; CYA=''; RST=''
fi

# 待测站点: 名称|URL|类型(trace=Cloudflare trace, plain=纯IP)
SITES=(
  "ChatGPT|https://chatgpt.com/cdn-cgi/trace|trace"
  "Claude|https://claude.ai/cdn-cgi/trace|trace"
  "Cloudflare|https://www.cloudflare.com/cdn-cgi/trace|trace"
  "ip.me|https://ip.me|plain"
)

# 从 trace 文本里取某个 key 的值
trace_val() { sed -nE "s/^$2=//p" <<<"$1" | head -n1; }

printf '%s探测当前网络出口%s' "${BOLD}" "${RST}"
[[ -n "${PROXY}" ]] && printf '  %s(proxy: %s)%s' "${DIM}" "${PROXY}" "${RST}"
printf '\n%s%s%s\n' "${DIM}" "$(printf '%.0s-' {1..64})" "${RST}"
printf '%-12s %-40s %s\n' "站点" "出口 IP" "地区/机房"
printf '%s%s%s\n' "${DIM}" "$(printf '%.0s-' {1..64})" "${RST}"

declare -A SEEN_IP
for entry in "${SITES[@]}"; do
  IFS='|' read -r name url kind <<<"${entry}"
  body="$(curl "${CURL_OPTS[@]}" "${url}" 2>/dev/null)"

  if [[ -z "${body}" ]]; then
    printf '%-12s %s%-40s%s %s\n' "${name}" "${RED}" "请求失败 / 超时" "${RST}" "-"
    continue
  fi

  if [[ "${kind}" == "trace" ]]; then
    ip="$(trace_val "${body}" ip)"
    loc="$(trace_val "${body}" loc)"
    colo="$(trace_val "${body}" colo)"
    warp="$(trace_val "${body}" warp)"
    extra="${loc:-?}"
    [[ -n "${colo}" ]] && extra+=" / ${colo}"
    [[ "${warp}" == "on" ]] && extra+=" ${YEL}(warp)${RST}"
  else
    ip="$(tr -d '[:space:]' <<<"${body}")"
    extra="${DIM}直连基准${RST}"
  fi

  # 颜色: IPv6 用青色, 重复出现的 IP 用绿色标注
  ipcolor="${CYA}"
  [[ "${ip}" == *.*.*.* ]] && ipcolor=''
  SEEN_IP["${ip}"]=$(( ${SEEN_IP["${ip}"]:-0} + 1 ))

  printf '%-12s %s%-40s%s %b\n' \
    "${name}" "${ipcolor}" "${ip:-未知}" "${RST}" "${extra}"
done

printf '%s%s%s\n' "${DIM}" "$(printf '%.0s-' {1..64})" "${RST}"

# 汇总: 出现了几个不同出口 IP
distinct="${#SEEN_IP[@]}"
if (( distinct <= 1 )); then
  printf '%s所有站点命中同一出口%s\n' "${GRN}" "${RST}"
else
  printf '%s共 %d 个不同出口 IP —— 各站点分流到了不同线路%s\n' \
    "${YEL}" "${distinct}" "${RST}"
fi
