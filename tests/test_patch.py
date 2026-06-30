"""patch（直用订阅 + 最小改写）单元测试。

运行： python3 tests/test_patch.py
仅依赖标准库与本项目 yamlmini，不需要 mihomo 内核或网络。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from mihomo_deploy.subscription import patch  # noqa: E402

# 一份"机场原配置"样本：含会被覆写的端口/控制器，与应保留的业务字段
SAMPLE = {
    "port": 7890,
    "socks-port": 7891,
    "mixed-port": 7893,
    "allow-lan": True,
    "external-controller": "0.0.0.0:9090",
    "mode": "rule",
    "dns": {"enable": True, "nameserver": ["223.5.5.5"]},
    "proxies": [
        {"name": "hk-01", "type": "ss", "server": "1.2.3.4", "port": 8388,
         "cipher": "aes-256-gcm", "password": "pw"},
    ],
    "proxy-groups": [
        {"name": "Proxies", "type": "select", "proxies": ["hk-01", "DIRECT"]},
    ],
    "rules": ["GEOIP,CN,DIRECT", "MATCH,Proxies"],
}

_failures = 0


def check(cond: bool, msg: str) -> None:
    global _failures
    status = "ok" if cond else "FAIL"
    if not cond:
        _failures += 1
    print(f"  [{status}] {msg}")


def test_minimal_rewrite() -> None:
    print("最小改写：覆写部署字段、保留业务字段")
    cfg = patch.apply(dict(SAMPLE), {"enable_tun": True})
    check(cfg["mixed-port"] == 7890, "mixed-port 统一为 7890")
    check("port" not in cfg and "socks-port" not in cfg, "删除冲突的 port/socks-port")
    check(cfg["external-controller"] == "127.0.0.1:9090", "控制器默认收回本机")
    check(cfg["allow-lan"] is False, "allow-lan 默认关")
    check(cfg["external-ui"].endswith("/ui"), "external-ui 指向 state/ui")
    check(cfg["profile"]["store-selected"] is True, "开启选组持久化")
    # 业务字段原样保留
    check(cfg["proxies"] == SAMPLE["proxies"], "proxies 原样保留")
    check(cfg["proxy-groups"] == SAMPLE["proxy-groups"], "proxy-groups 原样保留")
    check(cfg["rules"] == SAMPLE["rules"], "rules 原样保留")
    check(cfg["dns"] == SAMPLE["dns"], "订阅自带 dns 原样保留")


def test_tun_toggle() -> None:
    print("TUN 开关由部署层控制")
    on = patch.apply(dict(SAMPLE), {"enable_tun": True})
    check(on["tun"]["enable"] is True, "开启时 tun.enable=true")
    check(on["tun"]["device"] == "mihomo", "tun 设备名为 mihomo")
    check(on["tun"]["stack"] == "gvisor", "默认 stack=gvisor")
    off = patch.apply(dict(SAMPLE), {"enable_tun": False})
    check(off["tun"] == {"enable": False}, "关闭时仅 enable:false")


def test_lan_panel_guard() -> None:
    print("LAN 面板必须有 secret")
    try:
        patch.apply(dict(SAMPLE), {"lan_panel": True})
        check(False, "lan_panel 无 secret 应抛 PatchError")
    except patch.PatchError:
        check(True, "lan_panel 无 secret 被拒绝")
    ok = patch.apply(dict(SAMPLE), {"lan_panel": True, "secret": "s3cr3t"})
    check(ok["external-controller"] == "0.0.0.0:9090", "lan_panel 放开控制器")
    check(ok["secret"] == "s3cr3t", "写入 secret")


def test_lan_proxy() -> None:
    print("局域网代理")
    on = patch.apply(dict(SAMPLE), {"lan_proxy": True})
    check(on["allow-lan"] is True and on.get("bind-address") == "*", "lan_proxy 开放监听")


def test_default_dns_when_missing() -> None:
    print("订阅缺 dns 时注入默认")
    sample = {k: v for k, v in SAMPLE.items() if k != "dns"}
    cfg = patch.apply(sample, {"enable_tun": True})
    check(cfg["dns"]["enable"] is True, "注入默认 dns")
    check(cfg["dns"]["enhanced-mode"] == "fake-ip", "默认 fake-ip")


def test_reject_empty_proxies() -> None:
    print("无 proxies 应拒绝")
    try:
        patch.apply({"proxies": []}, {})
        check(False, "空 proxies 应抛 PatchError")
    except patch.PatchError:
        check(True, "空 proxies 被拒绝")


if __name__ == "__main__":
    for t in (
        test_minimal_rewrite, test_tun_toggle, test_lan_panel_guard,
        test_lan_proxy, test_default_dns_when_missing, test_reject_empty_proxies,
    ):
        t()
    print(f"\n{'全部通过' if _failures == 0 else f'{_failures} 项失败'}")
    sys.exit(1 if _failures else 0)
