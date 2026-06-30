"""定制层：state/customize.json 的默认值、加载/保存、交互式编辑。

mihomo 直用机场订阅，故定制层分两组（见 ARCHITECTURE.md §8）：

- **部署字段（始终生效）**：TUN / 局域网 / 面板 / 引导 DNS / 下载与转换后端等，
  由 subscription/patch.py 与 core.py 消费，决定如何把订阅改写成可部署的运行时配置。
- **分流叠加字段（仅 enable_overlay 时生效）**：AI / 流媒体 / 地区组等自定义分流，
  由 subscription/overlay.py 在订阅自带规则之上叠加；默认关闭，保持「直用机场分流」。

字段以 .get(key, 默认) 容错消费，故各模块不强依赖本文件键的完整性。
"""

from __future__ import annotations

import json
from typing import Any

from . import menu, paths, shell

# --------------------------------------------------------------------------- #
# 默认值
# --------------------------------------------------------------------------- #
# TUN 默认排除网段：本地 / 私网 / 常见 overlay（须与 subscription/patch.py 保持一致）
DEFAULT_TUN_ROUTE_EXCLUDE = [
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
    "169.254.0.0/16", "100.64.0.0/10", "::1/128", "fc00::/7", "fe80::/10",
]
AI_DOMAIN_SUFFIXES = [
    "openai.com", "chatgpt.com", "oaistatic.com", "oaiusercontent.com",
    "anthropic.com", "claude.ai", "gemini.google.com", "huggingface.co",
]
STREAMING_DOMAIN_SUFFIXES = [
    "netflix.com", "nflxvideo.net", "disneyplus.com", "dssott.com",
    "hbomax.com", "max.com", "primevideo.com", "youtube.com",
    "googlevideo.com", "spotify.com",
]
DEFAULT_PREFER_KEYWORDS = ["Singapore", "SG", "新加坡", "狮城"]
DEFAULT_HK_PREFER_KEYWORDS = ["Hong Kong", "HongKong", "HK", "香港"]
DEFAULT_SUBCONVERTER_BACKEND = "https://sub.v1.mk"

DEFAULTS: dict[str, Any] = {
    # —— 部署字段（始终生效）——
    "enable_tun": True,
    "tun_stack": "gvisor",
    "tun_route_exclude_cidrs": DEFAULT_TUN_ROUTE_EXCLUDE,
    "tun_exclude_uids": [],
    "lan_proxy": False,
    "lan_panel": False,
    "secret": "",
    "bootstrap_dns_server": "223.5.5.5",
    "bootstrap_dns_port": 53,
    "subconverter_backend": DEFAULT_SUBCONVERTER_BACKEND,
    "base64_local_fallback": False,
    "github_mirror": "",
    "download_proxy": "",
    "webui_port": 9091,
    # —— 地区自动测速聚合组（独立开关，不依赖 overlay）——
    "enable_region_groups": False,
    "generate_sg_groups": False,
    "generate_hk_groups": False,
    # —— 分流叠加字段（仅 enable_overlay 时生效）——
    "enable_overlay": False,
    "ai_domain_suffixes": AI_DOMAIN_SUFFIXES,
    "streaming_domain_suffixes": STREAMING_DOMAIN_SUFFIXES,
    "direct_domain_suffixes": [],
    "prefer_keywords": DEFAULT_PREFER_KEYWORDS,
    "hk_prefer_keywords": DEFAULT_HK_PREFER_KEYWORDS,
}


# --------------------------------------------------------------------------- #
# 加载 / 保存
# --------------------------------------------------------------------------- #
def load() -> dict[str, Any]:
    """读 customize.json，缺失字段以默认补全。"""
    data: dict[str, Any] = {}
    if paths.CUSTOMIZE_FILE.exists():
        try:
            data = json.loads(paths.CUSTOMIZE_FILE.read_text("utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            shell.warn(f"customize.json 读取失败，使用默认值：{exc}")
            data = {}
    merged = dict(DEFAULTS)
    if isinstance(data, dict):
        merged.update({k: v for k, v in data.items() if k in DEFAULTS})
    return merged


def save(cfg: dict[str, Any]) -> None:
    paths.ensure_state_dirs()
    paths.CUSTOMIZE_FILE.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", "utf-8"
    )


def ensure_exists() -> dict[str, Any]:
    """首次运行时落地默认 customize.json。"""
    cfg = load()
    if not paths.CUSTOMIZE_FILE.exists():
        save(cfg)
    return cfg


# --------------------------------------------------------------------------- #
# 交互式编辑（缓冲式：保存退出才写盘，^R 放弃）
# --------------------------------------------------------------------------- #
_LIST_FIELDS = {
    "tun_route_exclude_cidrs": "TUN 排除网段",
    "tun_exclude_uids": "TUN 排除 UID",
    "ai_domain_suffixes": "AI 域名后缀（叠加）",
    "streaming_domain_suffixes": "流媒体域名后缀（叠加）",
    "direct_domain_suffixes": "直连域名后缀（叠加）",
    "prefer_keywords": "新加坡关键词（叠加）",
    "hk_prefer_keywords": "香港关键词（叠加）",
}
_BOOL_FIELDS = {
    "enable_tun": "TUN 模式（全局透明代理）",
    "lan_proxy": "局域网代理（其他主机可用本机代理）",
    "lan_panel": "LAN 面板暴露",
    "enable_region_groups": "地区自动测速聚合组（SG/HK，可直接选用）",
    "generate_sg_groups": "├ 生成新加坡聚合组（SG-Auto）",
    "generate_hk_groups": "├ 生成香港聚合组（HK-Auto）",
    "enable_overlay": "启用自定义分流叠加（AI / 流媒体）",
    "base64_local_fallback": "base64 应急本地解析",
}
_SCALAR_FIELDS = {
    "tun_stack": "TUN 协议栈（gvisor/system/mixed）",
    "secret": "面板密钥 secret",
    "webui_port": "独立 Web 面板端口（根路径直开）",
    "bootstrap_dns_server": "引导 DNS 服务器",
    "bootstrap_dns_port": "引导 DNS 端口",
    "subconverter_backend": "subconverter 后端",
    "github_mirror": "GitHub 加速前缀",
    "download_proxy": "下载代理",
}

# 展示顺序：常用部署项在前，叠加分流项在后
_FIELD_ORDER = [
    "enable_tun",
    "tun_stack",
    "lan_proxy",
    "lan_panel",
    "secret",
    "webui_port",
    "download_proxy",
    "github_mirror",
    "subconverter_backend",
    "bootstrap_dns_server",
    "bootstrap_dns_port",
    "tun_route_exclude_cidrs",
    "tun_exclude_uids",
    "base64_local_fallback",
    "enable_region_groups",
    "generate_sg_groups",
    "generate_hk_groups",
    "prefer_keywords",
    "hk_prefer_keywords",
    "enable_overlay",
    "ai_domain_suffixes",
    "streaming_domain_suffixes",
    "direct_domain_suffixes",
]


def _summary(cfg: dict[str, Any], key: str) -> str:
    v = cfg.get(key, DEFAULTS.get(key))
    if isinstance(v, list):
        return f"{len(v)} 条" if v else "空"
    if isinstance(v, bool):
        return "开" if v else "关"
    return "未设置" if v in ("", None) else str(v)


def _field_label(cfg: dict[str, Any], key: str) -> str:
    if key in _LIST_FIELDS:
        return f"{_LIST_FIELDS[key]}（{_summary(cfg, key)}）"
    if key in _BOOL_FIELDS:
        return f"{_BOOL_FIELDS[key]}：{_summary(cfg, key)}"
    return f"{_SCALAR_FIELDS[key]}：{_summary(cfg, key)}"


def _edit_labels(cfg: dict[str, Any]) -> list[str]:
    return [_field_label(cfg, k) for k in _FIELD_ORDER]


def edit() -> bool:
    """交互式编辑 customize.json（缓冲式）。返回是否实际保存了改动。"""
    original = load()
    cfg = json.loads(json.dumps(original))  # 工作副本
    changed = False
    while True:
        try:
            idx = menu.select(
                "编辑定制层", _edit_labels(cfg),
                back_label="放弃修改并退出", save_label="保存并退出",
            )
        except menu.SaveExit:
            if not changed:
                shell.info("未做修改。")
                return False
            save(cfg)
            shell.ok("定制层已保存。")
            _sync_lan_proxy_firewall(original, cfg)
            return True
        except menu.Cancelled:
            if changed:
                shell.warn("已放弃本次修改（未写盘）。")
            return False
        key = _FIELD_ORDER[idx]
        if key in _LIST_FIELDS:
            changed |= _edit_list(cfg, key, _LIST_FIELDS[key])
        elif key in _BOOL_FIELDS:
            cfg[key] = not bool(cfg.get(key))
            changed = True
        else:
            changed |= _edit_scalar(cfg, key, _SCALAR_FIELDS[key])


def _sync_lan_proxy_firewall(original: dict[str, Any], cfg: dict[str, Any]) -> None:
    """lan_proxy 开关变化时，按需更新防火墙放行 7890 端口。"""
    before, after = bool(original.get("lan_proxy")), bool(cfg.get("lan_proxy"))
    if before == after:
        return
    from . import firewall
    if after:
        if menu.confirm("已开启局域网代理，更新防火墙放行 7890 端口？", default=True):
            firewall.allow(firewall.PROXY_PORT)
    else:
        if menu.confirm("已关闭局域网代理，撤销防火墙放行 7890 端口？", default=True):
            firewall.revoke(firewall.PROXY_PORT)


def _edit_list(cfg: dict[str, Any], key: str, label: str) -> bool:
    is_int = key == "tun_exclude_uids"
    changed = False
    while True:
        items = list(cfg.get(key, []))
        shell.info(f"{label}：当前 {len(items)} 条" + (("：" + ", ".join(str(x) for x in items)) if items else ""))
        try:
            act = menu.select(
                f"编辑 · {label}",
                ["添加一条", "删除一条", "批量粘贴替换（逗号/空格分隔）", "恢复默认", "清空"],
            )
        except menu.Cancelled:
            return changed
        try:
            if act == 0:
                val = menu.ask("新增值", allow_empty=False)
                items.append(int(val) if is_int else val)
            elif act == 1:
                if not items:
                    continue
                di = menu.select("删除哪一条", [str(x) for x in items])
                items.pop(di)
            elif act == 2:
                raw = menu.ask("粘贴（逗号或空格分隔）", allow_empty=True)
                toks = [t for t in raw.replace(",", " ").split() if t]
                items = [int(t) for t in toks] if is_int else toks
            elif act == 3:
                items = list(DEFAULTS.get(key, []))
            elif act == 4:
                items = []
        except (ValueError, menu.Cancelled):
            shell.warn("输入无效，已跳过。")
            continue
        cfg[key] = items
        changed = True


def _edit_scalar(cfg: dict[str, Any], key: str, label: str) -> bool:
    cur = str(cfg.get(key, "") or "")
    try:
        val = menu.ask(f"{label}（留空清除）", default=cur, allow_empty=True)
    except menu.Cancelled:
        return False
    if key in ("bootstrap_dns_port", "webui_port"):
        try:
            cfg[key] = int(val)
        except ValueError:
            shell.warn("端口需为整数，未修改。")
            return False
    else:
        cfg[key] = val
    return True


# --------------------------------------------------------------------------- #
# 独立调用
# --------------------------------------------------------------------------- #
def run(argv: list[str] | None = None) -> int:
    ensure_exists()
    edit()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
