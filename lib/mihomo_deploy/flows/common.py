"""flows 共享的交互助手。"""

from __future__ import annotations

import time

from .. import menu

# 菜单顺序即推荐优先级：Clash / mihomo 订阅优先
_SOURCE_OPTIONS = [
    "Clash / mihomo 订阅（★推荐：直用机场配置，凭证不外泄）",
    "通用 base64 订阅（经 subconverter 云端解析为 Clash）",
]
_SOURCE_TYPES = ["clash", "base64"]


def strip_scheme(proxy: str) -> str:
    """去掉 http:// / https:// 前缀，便于以 IP:端口 形式回显默认值。"""
    p = proxy.strip()
    return p.split("://", 1)[1] if "://" in p else p


def normalize_proxy(raw: str) -> str:
    """把用户输入的代理归一化为可用 URL：空→空；含 scheme 原样；否则补 http://。"""
    p = raw.strip()
    if not p:
        return ""
    if "://" in p:
        return p
    return "http://" + p


def ask_new_subscription() -> tuple[str, str, str, bool] | None:
    """交互收集新订阅信息：返回 (name, url, source_type, apply_overlay)。

    订阅链接留空 → 返回 None，表示"暂不配置订阅"（由上层决定结束初始化 / 取消添加）。
    任一步 ESC 抛 menu.Cancelled，由上层事务回退。
    """
    default_name = time.strftime("sub-%Y%m%d-%H%M%S")
    name = menu.ask("订阅名称，留空=时间戳", default=default_name)
    idx = menu.select("选择订阅来源类型", _SOURCE_OPTIONS)
    source_type = _SOURCE_TYPES[idx]
    url = menu.ask("订阅链接，留空=暂不配置", allow_empty=True)
    if not url:
        return None

    # 默认直用机场自带分流；叠加自定义分流为可选高级项
    apply_overlay = menu.confirm(
        "是否叠加自定义分流（AI / 流媒体 / 地区组）？\n"
        "  默认否＝直接沿用机场订阅自带的策略组与规则（推荐）。",
        default=False,
    )
    return name, url, source_type, apply_overlay
