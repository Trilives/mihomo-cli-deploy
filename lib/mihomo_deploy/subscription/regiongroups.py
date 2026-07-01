"""地区自动测速聚合组（可选增强，独立于 overlay）。

机场订阅通常已自带按地区分的 select 组（HK/SG/JP…，但需手动逐个挑节点）。本模块在其上
**额外**生成 url-test 聚合组（如 SG-Auto / HK-Auto）：按节点名关键词聚合该地区节点、自动
选最低延迟，并把聚合组插入主选择组前部，使其可直接作为出口选用——无需自己建分组。

与 overlay（AI / 流媒体自定义分流）相互独立：由 customize.enable_region_groups 单独开关，
不依赖 enable_overlay / 订阅级 apply_overlay。overlay 也复用本模块的基础函数构造同样的
地区组，故两者共存时不会重复建组（同名 url-test 组会被复用）。
"""

from __future__ import annotations

from typing import Any

# 主选择组定位关键词（与 node_select 一致）
_MAIN_GROUP_KEYWORDS = ("proxy", "节点选择", "节点", "选择", "select", "🚀", "手动")
_BUILTIN = {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE", "GLOBAL"}

# (启用字段, 关键词字段, 聚合组名)：开启对应字段才生成该地区聚合组
REGION_SPECS: list[tuple[str, str, str]] = [
    ("generate_sg_groups", "prefer_keywords", "SG-Auto"),
    ("generate_hk_groups", "hk_prefer_keywords", "HK-Auto"),
]


def _groups(config: dict) -> list[dict]:
    gs = config.get("proxy-groups")
    return [g for g in gs if isinstance(g, dict)] if isinstance(gs, list) else []


def _main_group_name(config: dict) -> str | None:
    selects = [g for g in _groups(config) if g.get("type") == "select"]
    if not selects:
        return None
    for g in selects:
        if any(kw in str(g.get("name", "")).lower() for kw in _MAIN_GROUP_KEYWORDS):
            return g.get("name")
    return max(selects, key=lambda g: len(g.get("proxies", []))).get("name")


def _uniq_name(base: str, taken: set[str]) -> str:
    name = base
    i = 1
    while name in taken:
        name = f"{base}-{i}"
        i += 1
    taken.add(name)
    return name


def _region_group(config: dict, keywords: list[str], tag: str, taken: set[str]) -> tuple[str, dict] | None:
    """按关键词从 proxies 筛节点，构造 url-test 地区组；无命中返回 None。"""
    names = [
        p["name"] for p in config.get("proxies", [])
        if isinstance(p, dict) and p.get("name")
        and any(k.lower() in str(p["name"]).lower() for k in keywords)
    ]
    if not names:
        return None
    name = _uniq_name(tag, taken)
    group = {
        "name": name, "type": "url-test", "proxies": names,
        "url": "https://www.gstatic.com/generate_204", "interval": 300, "tolerance": 50,
    }
    return name, group


def build(config: dict[str, Any], customize: dict[str, Any], taken: set[str]) -> list[tuple[str, dict | None]]:
    """按 customize 中开启的地区构造 url-test 聚合组。

    返回 [(组名, 组定义), ...]；组定义为 None 表示「同名 url-test 组已存在，复用即可」
    （避免与 overlay 等其它路径重复建组）。
    """
    existing = {g.get("name"): g for g in _groups(config)}
    out: list[tuple[str, dict | None]] = []
    for flag, kw_field, tag in REGION_SPECS:
        if not customize.get(flag):
            continue
        prior = existing.get(tag)
        if isinstance(prior, dict) and prior.get("type") == "url-test":
            out.append((tag, None))  # 复用已有同名聚合组
            continue
        r = _region_group(config, customize.get(kw_field) or [], tag, taken)
        if r:
            out.append(r)
    return out


def apply(config: dict[str, Any], customize: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """独立应用：生成地区聚合组并插入主选择组前部。返回 (config, info)。"""
    groups = _groups(config)
    taken = {str(g.get("name")) for g in groups if g.get("name")} | _BUILTIN
    built = build(config, customize, taken)
    names = [n for n, _ in built]
    if not names:
        return config, {"region_groups": []}

    new_groups = [g for _, g in built if g is not None]
    main = _main_group_name(config)
    if main:
        for g in groups:
            if g.get("name") == main and isinstance(g.get("proxies"), list):
                members = g["proxies"]
                add = [n for n in names if n not in members]
                g["proxies"] = [*add, *members]
                break
    config["proxy-groups"] = [*new_groups, *groups]
    return config, {"region_groups": names, "region_main": main}
