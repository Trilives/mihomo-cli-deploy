"""自定义分流叠加层（可选，默认关闭）。

在机场订阅自带的 proxy-groups / rules 之上**叠加**项目自定义分流，而非替换：
  - 新增 AI / Streaming 选择组（引用订阅主选择组 + 现有地区子组 + DIRECT）；
  - 可选按关键词从订阅节点筛出 SG / HK 地区 url-test 组；
  - 在 rules 头部插入 AI / 流媒体 / 直连域名规则（优先于订阅原规则命中）。

仅在 customize.enable_overlay=true 时由 manager 调用。引用的组名因机场而异，故主选择组
靠启发式定位，新组名遇冲突自动加后缀，尽量稳健。
"""

from __future__ import annotations

from typing import Any

# 与 node_select 一致的主选择组定位关键词
_MAIN_GROUP_KEYWORDS = ("proxy", "节点选择", "节点", "选择", "select", "🚀", "手动")
_BUILTIN = {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE", "GLOBAL"}


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


def apply(config: dict[str, Any], customize: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """在已 patch 的运行时配置上叠加自定义分流。返回 (config, info)。"""
    main = _main_group_name(config)
    if not main:
        # 没有可引用的主选择组，放弃叠加（保持订阅原状）
        return config, {"overlay": False, "overlay_reason": "未找到主选择组"}

    groups = _groups(config)
    taken = {g.get("name") for g in groups} | _BUILTIN
    new_groups: list[dict] = []

    # 可选地区组
    region_names: list[str] = []
    if customize.get("generate_sg_groups"):
        r = _region_group(config, customize.get("prefer_keywords") or [], "SG-Auto", taken)
        if r:
            region_names.append(r[0])
            new_groups.append(r[1])
    if customize.get("generate_hk_groups"):
        r = _region_group(config, customize.get("hk_prefer_keywords") or [], "HK-Auto", taken)
        if r:
            region_names.append(r[0])
            new_groups.append(r[1])

    members = [main, *region_names, "DIRECT"]
    ai_name = _uniq_name("AI", taken)
    streaming_name = _uniq_name("Streaming", taken)
    new_groups.append({"name": ai_name, "type": "select", "proxies": list(members)})
    new_groups.append({"name": streaming_name, "type": "select", "proxies": list(members)})

    direct_name = None
    direct_suffixes = customize.get("direct_domain_suffixes") or []

    # 叠加规则（插到 rules 头部，优先命中）
    new_rules: list[str] = []
    for suf in direct_suffixes:
        new_rules.append(f"DOMAIN-SUFFIX,{suf},DIRECT")
    for suf in customize.get("ai_domain_suffixes") or []:
        new_rules.append(f"DOMAIN-SUFFIX,{suf},{ai_name}")
    for suf in customize.get("streaming_domain_suffixes") or []:
        new_rules.append(f"DOMAIN-SUFFIX,{suf},{streaming_name}")

    config["proxy-groups"] = [*new_groups, *groups]
    config["rules"] = [*new_rules, *(config.get("rules") or [])]

    info = {
        "overlay": True,
        "overlay_main": main,
        "overlay_groups": [g["name"] for g in new_groups],
        "overlay_rules": len(new_rules),
    }
    return config, info
