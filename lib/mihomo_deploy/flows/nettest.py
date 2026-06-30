"""网络测试：经 Mihomo 本地代理探测延迟和出口 IP。"""

from __future__ import annotations

import socket
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import NamedTuple

from .. import keys, shell

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 7890
PROXY_URL = f"http://{PROXY_HOST}:{PROXY_PORT}"
UA = "Mozilla/5.0 (X11; Linux x86_64) mihomo-nettest"
MAX_TIME = 10

LATENCY_TARGETS: list[tuple[str, str, str]] = [
    ("流媒体", "Netflix", "https://www.netflix.com/title/80018499"),
    ("流媒体", "YouTube", "https://www.youtube.com/generate_204"),
    ("流媒体", "Disney+", "https://www.disneyplus.com/"),
    ("流媒体", "TikTok", "https://www.tiktok.com/"),
    ("站点", "Google", "https://www.google.com/generate_204"),
    ("站点", "GitHub", "https://github.com/"),
    ("站点", "Cloudflare", "https://www.cloudflare.com/cdn-cgi/trace"),
    ("AI", "OpenAI", "https://chat.openai.com/cdn-cgi/trace"),
    ("AI", "Claude", "https://claude.ai/cdn-cgi/trace"),
    ("AI", "Gemini", "https://gemini.google.com/"),
]

TRACE_TARGETS: list[tuple[str, str]] = [
    ("OpenAI", "https://chat.openai.com/cdn-cgi/trace"),
    ("Claude", "https://claude.ai/cdn-cgi/trace"),
    ("Cloudflare", "https://www.cloudflare.com/cdn-cgi/trace"),
]


class Latency(NamedTuple):
    ms: int | None
    code: str


def _proxy_up() -> bool:
    try:
        with socket.create_connection((PROXY_HOST, PROXY_PORT), timeout=1):
            return True
    except OSError:
        return False


def _curl(url: str, via_proxy: bool, fmt: str, *, body: bool) -> tuple[int, str]:
    import os
    args = ["curl", "-sS", "-A", UA, "--max-time", str(MAX_TIME), "-w", fmt]
    args += ["--proxy", PROXY_URL] if via_proxy else ["--noproxy", "*"]
    if not body:
        args += ["-o", os.devnull]
    args.append(url)
    result = shell.run(args, check=False, capture=True)
    return result.returncode, result.stdout or ""


def _latency(url: str, via_proxy: bool) -> Latency:
    rc, out = _curl(url, via_proxy, "%{time_starttransfer} %{http_code}", body=False)
    if rc != 0:
        return Latency(None, "ERR")
    parts = out.split()
    if len(parts) < 2:
        return Latency(None, "ERR")
    try:
        ms = int(round(float(parts[0]) * 1000))
    except ValueError:
        ms = None
    return Latency(ms, parts[1])


def _trace(url: str, via_proxy: bool) -> dict[str, str] | None:
    rc, out = _curl(url, via_proxy, "", body=True)
    if rc != 0:
        return None
    fields: dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            fields[key] = value
    return fields or None


def _run_pool(items, worker, label: str):
    total = len(items)
    results, done = {}, 0
    if not keys.interactive_tty():
        shell.info(f"{label}（{total} 项）...")
    with ThreadPoolExecutor(max_workers=min(12, total)) as executor:
        futures = {executor.submit(worker, item): item for item in items}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
            done += 1
            if keys.interactive_tty():
                sys.stdout.write(f"\r\033[K  {label}... {done}/{total}")
                sys.stdout.flush()
    if keys.interactive_tty():
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()
    return results


def run() -> None:
    shell.header("网络测试")
    via_proxy = _proxy_up()
    if via_proxy:
        shell.info(f"经本地代理 {PROXY_URL} 测试。")
    else:
        shell.warn(f"本地代理 {PROXY_URL} 未监听，改用直连测试。")

    latencies = _run_pool(LATENCY_TARGETS, lambda target: _latency(target[2], via_proxy), "延迟测试")
    print()
    last_cat = ""
    for cat, name, url in LATENCY_TARGETS:
        if cat != last_cat:
            shell.info(f"【{cat}】")
            last_cat = cat
        result = latencies[(cat, name, url)]
        mark = "OK" if result.ms is not None else "--"
        value = "超时" if result.ms is None else f"{result.ms}ms"
        print(f"  {mark} {name:<12} {value:>8}  (HTTP {result.code})")

    print()
    shell.info("【出口 IP / 落地】")
    traces = _run_pool(TRACE_TARGETS, lambda target: _trace(target[1], via_proxy), "出口探测")
    for name, url in TRACE_TARGETS:
        fields = traces[(name, url)]
        if not fields or "ip" not in fields:
            print(f"  -- {name:<12} 探测失败")
            continue
        colo = fields.get("colo", "")
        suffix = f" [{colo}]" if colo else ""
        print(f"  OK {name:<12} {fields['ip']:<22} 落地 {fields.get('loc', '?')}{suffix}")
    shell.ok("网络测试完成。")
    keys.read_line("回车返回主菜单... ")

