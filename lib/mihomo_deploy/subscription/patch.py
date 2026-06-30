"""直用订阅 + 最小改写：把机场原生 Clash/mihomo 订阅改写为可部署的运行时配置。

这是 mihomo 版与 sing-box 版的根本差异（见 ARCHITECTURE.md §5）：
**不做协议转换、不重建分流**。订阅自带的 proxies / proxy-groups / rules /
rule-providers / proxy-providers / dns 全部原样保留，只覆写「部署/运行时」必需字段：

  - 本地代理端口（统一 mixed-port=7890，删除冲突的 port/socks-port/redir-port）
  - 局域网开关（allow-lan / bind-address，由 lan_proxy 决定）
  - 外部控制器与面板（external-controller / external-ui / secret，由 lan_panel 决定）
  - TUN（按 enable_tun 整段覆写，由本部署层统一控制）
  - 选组持久化（profile.store-selected）
  - DNS（订阅自带则保留；缺失时注入可用的最小默认，TUN 模式需要）

输出为普通 dict，由调用方用 json.dumps 写成 config.yaml（JSON 是合法 YAML，
mihomo 直接解析，省掉 YAML dumper）。
"""

from __future__ import annotations

from typing import Any

from .. import paths, yamlmini

MIXED_PORT = 7890
CONTROLLER_PORT = 9090
TUN_DEVICE = "mihomo"
DEFAULT_BOOTSTRAP_DNS = "223.5.5.5"
# 默认 TUN 排除网段：本地 / 私网 / 常见 overlay（Tailscale 等），避免被 TUN 劫持
DEFAULT_TUN_ROUTE_EXCLUDE = [
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
    "169.254.0.0/16", "100.64.0.0/10", "::1/128", "fc00::/7", "fe80::/10",
]


class PatchError(Exception):
    pass


def _truthy(cfg: dict[str, Any], key: str, default: bool = False) -> bool:
    return bool(cfg.get(key, default))


def _build_tun(customize: dict[str, Any]) -> dict[str, Any]:
    """按 enable_tun 构造 tun 段。关闭时仅 enable:false（纯代理模式）。"""
    if not _truthy(customize, "enable_tun", True):
        return {"enable": False}
    exclude = list(customize.get("tun_route_exclude_cidrs") or DEFAULT_TUN_ROUTE_EXCLUDE)
    tun: dict[str, Any] = {
        "enable": True,
        "stack": str(customize.get("tun_stack") or "gvisor"),
        "device": TUN_DEVICE,
        "auto-route": True,
        "auto-detect-interface": True,
        "dns-hijack": ["any:53"],
        "route-exclude-address": exclude,
    }
    uids = customize.get("tun_exclude_uids") or []
    if uids:
        # mihomo 用 include/exclude 包级路由；UID 排除经 so-mark/规则，留作占位字段
        tun["exclude-uid"] = [int(u) for u in uids]
    return tun


def _default_dns(customize: dict[str, Any]) -> dict[str, Any]:
    """订阅无 dns 段时注入的最小可用默认（fake-ip，配合 TUN）。"""
    bootstrap = str(customize.get("bootstrap_dns_server") or DEFAULT_BOOTSTRAP_DNS)
    return {
        "enable": True,
        "listen": "0.0.0.0:1053",
        "ipv6": False,
        "enhanced-mode": "fake-ip",
        "fake-ip-range": "198.18.0.1/16",
        "fake-ip-filter": ["*.lan", "*.local", "localhost.ptlogin2.qq.com"],
        "default-nameserver": [bootstrap],
        "nameserver": [bootstrap, "https://doh.pub/dns-query"],
        "fallback": ["https://1.1.1.1/dns-query", "https://dns.google/dns-query"],
    }


def apply(clash: dict[str, Any], customize: dict[str, Any]) -> dict[str, Any]:
    """对机场 Clash 订阅 dict 做最小改写，返回运行时 mihomo 配置 dict。

    入参 clash 会被浅改写（原 dict 不再使用）；业务字段原样保留。
    """
    if not isinstance(clash, dict):
        raise PatchError("订阅根必须是映射（YAML mapping）。")
    if not isinstance(clash.get("proxies"), list) or not clash["proxies"]:
        raise PatchError("订阅缺少 proxies 列表或为空，无法作为 mihomo 配置。")

    cfg = dict(clash)  # 浅拷贝，业务字段引用保留

    # 1. 本地代理端口：统一 mixed-port，删除会冲突的其它入站端口
    cfg.pop("port", None)
    cfg.pop("socks-port", None)
    cfg.pop("redir-port", None)
    cfg.pop("tproxy-port", None)
    cfg["mixed-port"] = MIXED_PORT

    # 2. 局域网代理
    lan_proxy = _truthy(customize, "lan_proxy", False)
    cfg["allow-lan"] = lan_proxy
    if lan_proxy:
        cfg["bind-address"] = "*"
    else:
        cfg.pop("bind-address", None)

    # 3. 外部控制器 + 面板（默认仅本机；lan_panel 才放开）
    lan_panel = _truthy(customize, "lan_panel", False)
    host = "0.0.0.0" if lan_panel else "127.0.0.1"
    cfg["external-controller"] = f"{host}:{CONTROLLER_PORT}"
    cfg["external-ui"] = str(paths.UI_DIR)
    secret = str(customize.get("secret") or "")
    if secret:
        cfg["secret"] = secret
    elif lan_panel:
        raise PatchError("已开启 LAN 面板（lan_panel）但未设置 secret，拒绝在无密钥下放开控制器。")
    else:
        cfg.pop("secret", None)

    # 4. mode / log-level 缺省兜底（订阅有则保留）
    cfg.setdefault("mode", "rule")
    cfg.setdefault("log-level", "warning")

    # 5. 选组持久化
    profile = dict(cfg.get("profile") or {})
    profile["store-selected"] = True
    cfg["profile"] = profile

    # 6. TUN：由本部署层整段覆写
    cfg["tun"] = _build_tun(customize)

    # 7. DNS：订阅自带则保留；缺失才注入默认（TUN 模式需要可用 DNS）
    if not isinstance(cfg.get("dns"), dict) or not cfg["dns"]:
        cfg["dns"] = _default_dns(customize)

    return cfg


def summarize(config: dict[str, Any]) -> dict[str, Any]:
    """运行时配置 → 概要信息（节点 / 策略组 / 规则数 / TUN）。"""
    return {
        "proxies": len(config.get("proxies", [])),
        "proxy_groups": len(config.get("proxy-groups", [])),
        "rules": len(config.get("rules", [])),
        "tun": bool(config.get("tun", {}).get("enable")),
    }


def build(clash: dict[str, Any], customize: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Clash 配置 dict → (运行时配置 dict, 概要信息)。"""
    if not isinstance(clash, dict):
        raise PatchError("订阅根必须是映射。")
    has_dns = isinstance(clash.get("dns"), dict) and bool(clash.get("dns"))
    cfg = apply(clash, customize)
    info = summarize(cfg)
    info["dns_from_subscription"] = has_dns
    return cfg, info


def from_clash_yaml(yaml_text: str, customize: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Clash YAML 文本 → (运行时配置 dict, 概要信息)。"""
    data = yamlmini.load(yaml_text)
    if not isinstance(data, dict):
        raise PatchError("订阅 YAML 根必须是映射。")
    return build(data, customize)
