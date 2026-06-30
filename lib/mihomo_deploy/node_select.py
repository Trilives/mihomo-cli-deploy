"""交互式切换 / 固定 Mihomo 节点。"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from . import keys, menu, paths, service, shell, yamlmini
from .subscription import manager

GROUP_TYPES = {"select", "url-test", "fallback", "load-balance"}
INFO_KEYWORDS = ("Traffic:", "Expire:", "剩余流量", "过期时间", "套餐", "官网", "订阅", "重置")
REGIONS = [
    ("hk", "香港", ("香港", "hong kong", "hongkong", "hk")),
    ("tw", "台湾", ("台湾", "臺灣", "taiwan", "tw")),
    ("jp", "日本", ("日本", "japan", "东京", "大阪", "jp")),
    ("kr", "韩国", ("韩国", "韓國", "korea", "首尔", "kr")),
    ("sg", "新加坡", ("新加坡", "singapore", "狮城", "sg")),
    ("us", "美国", ("美国", "united states", "america", "硅谷", "洛杉矶", "us")),
]
OTHER_KEY, OTHER_LABEL = "other", "其他地区"
DELAY_URL = "https://www.gstatic.com/generate_204"
DELAY_TIMEOUT_MS = 5000


def _is_info(name: str) -> bool:
    return any(key in name for key in INFO_KEYWORDS)


def _classify(name: str) -> str:
    low = name.lower()
    for key, _label, kws in REGIONS:
        if any(kw in name or kw in low for kw in kws):
            return key
    return OTHER_KEY


def _groups(config: dict[str, Any]) -> list[dict[str, Any]]:
    groups = config.get("proxy-groups")
    return groups if isinstance(groups, list) else []


def pick_group(config: dict[str, Any], forced: str = "") -> dict[str, Any]:
    selectors = [g for g in _groups(config) if isinstance(g, dict) and g.get("type") in GROUP_TYPES and isinstance(g.get("proxies"), list)]
    if not selectors:
        raise RuntimeError("配置里没有可切换的 proxy-groups。")
    if forced:
        for g in selectors:
            if g.get("name") == forced:
                return g
        raise RuntimeError(f"指定分组不存在: {forced}")
    for g in selectors:
        if g.get("name") in ("Proxy", "PROXY", "🚀 节点选择"):
            return g
    return max(selectors, key=lambda g: len(g.get("proxies", [])))


def collect_members(config: dict[str, Any], group: dict[str, Any]) -> tuple[dict[str, list[str]], list[str]]:
    group_names = {g.get("name") for g in _groups(config) if isinstance(g, dict)}
    proxy_names = {p.get("name") for p in config.get("proxies", []) if isinstance(p, dict)}
    buckets: dict[str, list[str]] = {}
    nested: list[str] = []
    for item in group.get("proxies", []):
        if not isinstance(item, str) or item in ("DIRECT", "REJECT", "GLOBAL") or _is_info(item):
            continue
        if item in group_names and item not in proxy_names:
            nested.append(item)
        else:
            buckets.setdefault(_classify(item), []).append(item)
    return buckets, nested


def _clash_base(config: dict[str, Any]) -> tuple[str, dict[str, str]] | None:
    controller = str(config.get("external-controller") or "").strip()
    if not controller:
        return None
    host, _, port = controller.partition(":")
    if host in ("", "0.0.0.0", "::"):
        host = "127.0.0.1"
    headers = {"Content-Type": "application/json"}
    secret = str(config.get("secret") or "")
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    return f"http://{host}:{port or '9090'}", headers


def _api_reachable(base: str, headers: dict[str, str]) -> bool:
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{base}/version", headers=headers), timeout=2):
            return True
    except (urllib.error.URLError, OSError):
        return False


def _api_switch(base: str, headers: dict[str, str], group: str, node: str) -> bool:
    body = json.dumps({"name": node}).encode()
    req = urllib.request.Request(f"{base}/proxies/{urllib.parse.quote(group)}", data=body, headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=4):
            return True
    except (urllib.error.URLError, OSError) as exc:
        shell.warn(f"Clash API 实时切换失败：{exc}")
        return False


def _api_delay(base: str, headers: dict[str, str], name: str) -> int | None:
    q = urllib.parse.urlencode({"url": DELAY_URL, "timeout": DELAY_TIMEOUT_MS})
    url = f"{base}/proxies/{urllib.parse.quote(name)}/delay?{q}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=DELAY_TIMEOUT_MS / 1000 + 2) as resp:
            value = json.load(resp).get("delay")
            return int(value) if value is not None else None
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return None


def _measure(api: tuple[str, dict[str, str]], names: list[str]) -> dict[str, int | None]:
    if not names:
        return {}
    base, headers = api
    results: dict[str, int | None] = {}
    done = 0
    total = len(names)
    with ThreadPoolExecutor(max_workers=min(16, total)) as executor:
        futures = {executor.submit(_api_delay, base, headers, name): name for name in names}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
            done += 1
            if keys.interactive_tty():
                sys.stdout.write(f"\r\033[K  测速中... {done}/{total}")
                sys.stdout.flush()
    if keys.interactive_tty():
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()
    return results


def _fmt_delay(ms: int | None) -> str:
    return "超时" if ms is None else f"{ms}ms"


def _dump_scalar(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "" or any(ch in text for ch in [":", "#", "{", "}", "[", "]", ","]) or text.strip() != text:
        return '"' + text.replace('"', '\\"') + '"'
    return text


def _dump_yaml(value: Any, indent: int = 0) -> list[str]:
    pad = " " * indent
    if isinstance(value, dict):
        out: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                out.append(f"{pad}{key}:")
                out.extend(_dump_yaml(item, indent + 2))
            else:
                out.append(f"{pad}{key}: {_dump_scalar(item)}")
        return out
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, (dict, list)):
                out.append(f"{pad}-")
                out.extend(_dump_yaml(item, indent + 2))
            else:
                out.append(f"{pad}- {_dump_scalar(item)}")
        return out
    return [f"{pad}{_dump_scalar(value)}"]


def _persist_first(config: dict[str, Any], group_name: str, node: str, targets: list[Path]) -> None:
    for group in _groups(config):
        if isinstance(group, dict) and group.get("name") == group_name and isinstance(group.get("proxies"), list):
            group["proxies"] = [node] + [item for item in group["proxies"] if item != node]
            break
    payload = "\n".join(_dump_yaml(config)) + "\n"
    for target in targets:
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(payload, "utf-8")
        tmp.replace(target)


def select(config_path: str | None = None, group: str = "") -> None:
    path = Path(config_path) if config_path else paths.CONFIG_FILE
    if not path.is_file():
        raise RuntimeError(f"找不到配置文件：{path}")
    config = yamlmini.load(path.read_text("utf-8"))
    if not isinstance(config, dict):
        raise RuntimeError("配置不是 YAML mapping。")
    target = pick_group(config, group)
    group_name = str(target["name"])
    buckets, nested_groups = collect_members(config, target)
    if not buckets and not nested_groups:
        raise RuntimeError(f"分组 {group_name} 下没有可选节点。")

    api = _clash_base(config)
    api_ok = bool(api and _api_reachable(*api))
    shell.info("已连上 Mihomo Clash API，列表将实时测速。" if api_ok else "Clash API 不可达，跳过测速。")

    first_menu: list[tuple[str, list[str]]] = []
    for key, label, _kws in REGIONS:
        if buckets.get(key):
            first_menu.append((label, buckets[key]))
    if buckets.get(OTHER_KEY):
        first_menu.append((OTHER_LABEL, buckets[OTHER_KEY]))
    if nested_groups:
        first_menu.append(("分组", nested_groups))
    idx = menu.select("选择地区 / 分组", [f"{label}（{len(items)}）" for label, items in first_menu])
    label, items = first_menu[idx]
    delays = _measure(api, items) if api_ok and api else {}
    labels = [f"{name}   {_fmt_delay(delays.get(name))}" if api_ok else name for name in items]
    selected = items[menu.select(label, labels)]

    targets = [path]
    active = manager.get_active()
    if active:
        sub_cfg = paths.subscription_dir(active.name) / "config.yaml"
        if sub_cfg.exists() and sub_cfg != path:
            targets.append(sub_cfg)
    _persist_first(config, group_name, selected, targets)
    shell.ok(f"已固定 {group_name} 首选 = {selected}")
    if api_ok and api and _api_switch(api[0], api[1], group_name, selected):
        shell.ok(f"已实时切换 {group_name} -> {selected}")
    if service.is_installed() and menu.confirm("重启服务以确保生效？", default=False):
        service.sync_and_restart()


def run(argv: list[str] | None = None) -> int:
    try:
        select()
    except menu.Cancelled:
        return 0
    except RuntimeError as exc:
        shell.error(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())

