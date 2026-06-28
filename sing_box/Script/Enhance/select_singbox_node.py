#!/usr/bin/env python3
"""Interactive sing-box node selector.

本质上是“把选中项设为代理分组（默认 Proxy）的第一个成员”的脚本：sing-box
selector 在没有持久化选择时取第一个成员，把它固定下来后，其他脚本重启
sing-box 时就不会被 SG-Auto 之类的 urltest 自动测速组乱切节点。

三步式终端交互：
  1. 选地区（主要国家/地区，其余归入“其他”）或“分组”（列出子分组如 SG-Auto）
  2. 选具体节点 / 分组
  3. 选是否运行 Script/setup_sing_box_service.sh 重启服务（需 sudo）

设计目标是尽量兼容不同 config.json：
  - 自动探测主代理分组（优先名为 Proxy 的 selector，否则成员最多的 selector）。
  - 成员直接取该 selector 的列表：叶子节点按地区分桶，子分组单列。
  - 把选中项移到该分组成员第一位，并对齐 `default`（default 优先级更高，
    不对齐会盖掉第一位），使选择在重启后仍生效。
  - 服务在运行时还会通过 Clash API（地址/密钥读自 experimental.clash_api）实时切换。
  - 仅依赖 Python3 标准库，无需 jq/curl。

用法：
  ./sing_box/Script/Enhance/select_singbox_node.py [config.json]
环境变量：
  SINGBOX_GROUP    强制指定要切换的分组名（覆盖自动探测）
  RESTART_ARGS     透传给 setup_sing_box_service.sh 的额外参数（如 "-n my-singbox"）
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import NoReturn

# 本脚本位于 sing_box/Script/Enhance/，据此回推其他路径。
ENHANCE_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = ENHANCE_DIR.parent            # sing_box/Script
SING_BOX_DIR = SCRIPT_DIR.parent           # sing_box
DEFAULT_CONFIG = SING_BOX_DIR / "config.json"
SETUP_SCRIPT = SCRIPT_DIR / "setup_sing_box_service.sh"

GROUP_TYPES = {"selector", "urltest"}
# 非真实节点的出站类型，分组成员里出现时跳过。
NON_NODE_TYPES = {"direct", "block", "dns"}
# 订阅说明“伪节点”，按关键词过滤。
INFO_KEYWORDS = ("Traffic:", "Expire:", "剩余流量", "过期时间", "剩余", "套餐", "官网", "订阅", "重置")

# 主要地区：(key, 显示名, 匹配关键词, 国旗 emoji)。按此顺序展示。
REGIONS = [
    ("hk", "🇭🇰 香港", ("香港", "hong kong", "hongkong"), "🇭🇰"),
    ("tw", "🇹🇼 台湾", ("台湾", "臺灣", "taiwan"), "🇹🇼"),
    ("jp", "🇯🇵 日本", ("日本", "japan", "东京", "大阪"), "🇯🇵"),
    ("kr", "🇰🇷 韩国", ("韩国", "韓國", "korea", "首尔"), "🇰🇷"),
    ("sg", "🇸🇬 新加坡", ("新加坡", "singapore", "狮城", "獅城"), "🇸🇬"),
    ("us", "🇺🇸 美国", ("美国", "united states", "america", "硅谷", "洛杉矶", "圣何塞"), "🇺🇸"),
]
OTHER_KEY = "other"
OTHER_LABEL = "🌐 其他地区"


def die(msg: str, code: int = 1) -> NoReturn:
    print(f"\033[31m错误：{msg}\033[0m", file=sys.stderr)
    sys.exit(code)


def load_config(path: Path) -> dict:
    if not path.is_file():
        die(f"找不到配置文件：{path}")
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        die(f"读取配置失败：{exc}")


def pick_group(config: dict) -> dict:
    """选出要切换的 selector 分组。"""
    selectors = [o for o in config.get("outbounds", []) if o.get("type") == "selector"]
    if not selectors:
        die("配置里没有 selector 分组，无法切换节点。")

    forced = os.environ.get("SINGBOX_GROUP")
    if forced:
        for o in selectors:
            if o.get("tag") == forced:
                return o
        die(f"SINGBOX_GROUP 指定的分组 '{forced}' 不存在。")

    for o in selectors:
        if o.get("tag") == "Proxy":
            return o
    # 退而求其次：成员最多的 selector。
    return max(selectors, key=lambda o: len(o.get("outbounds", [])))


def classify(tag: str) -> str:
    low = tag.lower()
    for key, _label, keywords, _flag in REGIONS:
        if any(kw in tag or kw in low for kw in keywords):
            return key
    for key, _label, _keywords, flag in REGIONS:
        if flag and flag in tag:
            return key
    return OTHER_KEY


def is_info(tag: str) -> bool:
    return any(kw in tag for kw in INFO_KEYWORDS)


def collect_members(config: dict, group: dict) -> "tuple[dict[str, list[str]], list[str]]":
    """把目标分组的成员拆成 (按地区分桶的叶子节点, 子分组列表)。"""
    type_by_tag = {o.get("tag"): o.get("type") for o in config.get("outbounds", [])}
    buckets: dict[str, list[str]] = {}
    groups: list[str] = []
    for tag in group.get("outbounds", []):
        otype = type_by_tag.get(tag)
        if otype in GROUP_TYPES:
            groups.append(tag)
        elif otype in NON_NODE_TYPES or is_info(tag):
            continue
        else:
            buckets.setdefault(classify(tag), []).append(tag)
    return buckets, groups


def ask_choice(prompt: str, count: int, *, allow_back: bool) -> "int | str | None":
    """返回 0-based 索引；'b' 返回上一步；None 表示退出。"""
    hints = "输入序号"
    if allow_back:
        hints += "，b 返回上一步"
    hints += "，q 退出"
    while True:
        try:
            raw = input(f"{prompt}（{hints}）: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw in ("q", "quit", "exit"):
            return None
        if allow_back and raw in ("b", "back"):
            return "back"
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < count:
                return idx
        print("  无效输入，请重试。")


def clash_base(config: dict) -> "tuple[str, dict] | None":
    api = config.get("experimental", {}).get("clash_api") or {}
    controller = api.get("external_controller")
    if not controller:
        return None
    host, _, port = controller.partition(":")
    if host in ("", "0.0.0.0", "::"):
        host = "127.0.0.1"
    base = f"http://{host}:{port or '9090'}"
    headers = {"Content-Type": "application/json"}
    secret = api.get("secret")
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    return base, headers


def api_reachable(base: str, headers: dict) -> bool:
    try:
        req = urllib.request.Request(f"{base}/version", headers=headers)
        with urllib.request.urlopen(req, timeout=2):
            return True
    except (urllib.error.URLError, OSError):
        return False


def api_switch(base: str, headers: dict, group: str, node: str) -> bool:
    body = json.dumps({"name": node}).encode()
    req = urllib.request.Request(
        f"{base}/proxies/{urllib.parse.quote(group)}",
        data=body, headers=headers, method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=4):
            return True
    except urllib.error.HTTPError as exc:
        print(f"  Clash API 返回 {exc.code}：{exc.read().decode(errors='replace')[:200]}")
    except (urllib.error.URLError, OSError) as exc:
        print(f"  Clash API 调用失败：{exc}")
    return False


def persist_first(path: Path, config: dict, group_tag: str, node: str) -> None:
    """把 node 移到目标分组成员的第一位，并对齐 default。

    sing-box selector 在没有持久化选择时取第一个成员；但若存在 default，则
    default 优先级更高。因此两者都设成 node，重启后才稳定停在该项、不会被
    SG-Auto 之类的 urltest 自动测速组乱切。
    """
    for o in config.get("outbounds", []):
        if o.get("type") == "selector" and o.get("tag") == group_tag:
            members = [t for t in o.get("outbounds", []) if t != node]
            o["outbounds"] = [node] + members
            o["default"] = node
            break
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    tmp.replace(path)


def restart_service() -> None:
    if not SETUP_SCRIPT.is_file():
        die(f"找不到重启脚本：{SETUP_SCRIPT}")
    extra = os.environ.get("RESTART_ARGS", "").split()
    cmd = ["sudo", "bash", str(SETUP_SCRIPT)] + extra
    print(f"\n运行：{' '.join(cmd)}")
    print("（如有提示请输入 sudo 密码）\n")
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        die(f"重启脚本退出码 {rc}", rc)


def main() -> None:
    config_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_CONFIG
    config = load_config(config_path)
    group = pick_group(config)
    group_tag = group["tag"]

    buckets, groups = collect_members(config, group)
    if not buckets and not groups:
        die(f"分组 '{group_tag}' 下没有可选项。")

    total = sum(len(v) for v in buckets.values())
    print(f"\n配置文件：{config_path}")
    print(f"目标分组：{group_tag}（{total} 个节点，{len(groups)} 个子分组）\n")

    # 第一步菜单：有节点的主要地区 + 其他 + 分组。空项不显示。
    menu: list[tuple[str, str, list[str]]] = []
    for key, label, _kw, _f in REGIONS:
        if buckets.get(key):
            menu.append((key, label, buckets[key]))
    if buckets.get(OTHER_KEY):
        menu.append((OTHER_KEY, OTHER_LABEL, buckets[OTHER_KEY]))
    if groups:
        menu.append(("__groups__", "🧭 分组（自动测速 / 故障转移等）", groups))

    selected = None
    while selected is None:
        # 第一步：选地区或分组
        print("第 1 步 · 选择地区 / 分组")
        for i, (_key, label, items) in enumerate(menu, 1):
            print(f"  {i}) {label}  ({len(items)})")
        choice = ask_choice("请选择", len(menu), allow_back=False)
        if not isinstance(choice, int):
            print("已取消。")
            return
        _key, label, items = menu[choice]

        # 第二步：选具体节点 / 分组
        while True:
            print(f"\n第 2 步 · {label}")
            for i, tag in enumerate(items, 1):
                print(f"  {i}) {tag}")
            choice = ask_choice("请选择", len(items), allow_back=True)
            if choice is None:
                print("已取消。")
                return
            if not isinstance(choice, int):  # "back"
                print()
                break
            selected = items[choice]
            break

    print(f"\n已选择：{selected}")

    # 应用：把它设为 {group_tag} 的第一个成员（核心动作）+ 若服务在跑则实时切换。
    persist_first(config_path, config, group_tag, selected)
    print(f"  ✓ 已写入 {config_path}：{group_tag} 第一个成员 = default = {selected}")
    api = clash_base(config)
    if api and api_reachable(*api):
        if api_switch(api[0], api[1], group_tag, selected):
            print(f"  ✓ 已通过 Clash API 实时切换 {group_tag} → {selected}")
    else:
        print("  · Clash API 不可达（服务未运行？），重启后由配置生效。")

    # 第三步：是否重启
    print("\n第 3 步 · 是否运行 setup_sing_box_service.sh 重启服务？")
    try:
        ans = input("重启服务以确保生效？[y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        ans = ""
        print()
    if ans in ("y", "yes"):
        restart_service()
        print("\n✓ 完成：节点已切换并重启服务。")
    else:
        print("\n✓ 完成：节点已切换（未重启）。")


if __name__ == "__main__":
    main()
