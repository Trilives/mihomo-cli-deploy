"""自定义分流叠加层（可选，默认关闭）。

在机场订阅自带的 proxy-groups / rules 之上**叠加**项目自定义分流，而非替换：
  - 新增 AI / Streaming 选择组（引用订阅主选择组 + 现有地区子组 + DIRECT）；
  - 可选按关键词从订阅节点筛出 SG / HK 地区 url-test 组（复用 regiongroups）；
  - 在 rules 头部插入 AI / 流媒体 / 直连域名规则（优先于订阅原规则命中）。

仅在 customize.enable_overlay=true 时由 manager 调用。引用的组名因机场而异，故主选择组
靠启发式定位，新组名遇冲突自动加后缀，尽量稳健。地区聚合组的构造委托给 regiongroups，
与「独立地区聚合组」功能共用同一套逻辑，两者共存时不会重复建组。
"""

from __future__ import annotations

from typing import Any

from . import regiongroups
from .regiongroups import _BUILTIN, _groups, _main_group_name, _uniq_name


def apply(config: dict[str, Any], customize: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """在已 patch 的运行时配置上叠加自定义分流。返回 (config, info)。"""
    main = _main_group_name(config)
    if not main:
        # 没有可引用的主选择组，放弃叠加（保持订阅原状）
        return config, {"overlay": False, "overlay_reason": "未找到主选择组"}

    groups = _groups(config)
    taken = {str(g.get("name")) for g in groups if g.get("name")} | _BUILTIN
    new_groups: list[dict] = []

    # 可选地区组（委托 regiongroups 构造，保持与独立功能一致）
    region_names: list[str] = []
    for name, group in regiongroups.build(config, customize, taken):
        region_names.append(name)
        if group is not None:
            new_groups.append(group)

    members = [main, *region_names, "DIRECT"]
    ai_name = _uniq_name("AI", taken)
    streaming_name = _uniq_name("Streaming", taken)
    new_groups.append({"name": ai_name, "type": "select", "proxies": list(members)})
    new_groups.append({"name": streaming_name, "type": "select", "proxies": list(members)})

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
