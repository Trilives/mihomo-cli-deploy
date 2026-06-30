"""overlay（自定义分流叠加）单元测试。

运行： python3 tests/test_overlay.py
仅依赖标准库与本项目，不需要 mihomo 内核或网络。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from mihomo_deploy.subscription import overlay  # noqa: E402

BASE = {
    "proxies": [
        {"name": "HK-01", "type": "ss"},
        {"name": "SG-01", "type": "ss"},
        {"name": "US-01", "type": "ss"},
    ],
    "proxy-groups": [
        {"name": "Proxies", "type": "select", "proxies": ["HK-01", "SG-01", "US-01", "DIRECT"]},
    ],
    "rules": ["GEOIP,CN,DIRECT", "MATCH,Proxies"],
}

CUSTOMIZE = {
    "ai_domain_suffixes": ["openai.com", "claude.ai"],
    "streaming_domain_suffixes": ["netflix.com"],
    "direct_domain_suffixes": ["example.cn"],
    "generate_sg_groups": True,
    "prefer_keywords": ["SG", "新加坡"],
    "generate_hk_groups": True,
    "hk_prefer_keywords": ["HK", "香港"],
}

_failures = 0


def check(cond: bool, msg: str) -> None:
    global _failures
    if not cond:
        _failures += 1
    print(f"  [{'ok' if cond else 'FAIL'}] {msg}")


def test_overlay_apply() -> None:
    print("叠加 AI/Streaming/地区组 + 规则")
    import copy
    config, info = overlay.apply(copy.deepcopy(BASE), CUSTOMIZE)
    check(info["overlay"] is True, "overlay 生效")
    check(info["overlay_main"] == "Proxies", "定位主选择组 Proxies")
    names = [g["name"] for g in config["proxy-groups"]]
    check("AI" in names and "Streaming" in names, "新增 AI / Streaming 组")
    check("SG-Auto" in names and "HK-Auto" in names, "新增 SG/HK 地区组")
    # 规则插到头部，优先命中
    head = config["rules"][:6]
    check(any("openai.com" in r and r.endswith(",AI") for r in head), "AI 规则在前")
    check(any("netflix.com" in r and r.endswith(",Streaming") for r in head), "流媒体规则在前")
    check(any("example.cn" in r and r.endswith(",DIRECT") for r in head), "直连规则在前")
    check(config["rules"][-1] == "MATCH,Proxies", "订阅原规则保留在后")
    # 地区组成员按关键词筛
    sg = next(g for g in config["proxy-groups"] if g["name"] == "SG-Auto")
    check(sg["proxies"] == ["SG-01"], "SG 组按关键词筛节点")


def test_no_main_group() -> None:
    print("无主选择组时放弃叠加")
    config, info = overlay.apply({"proxies": [], "proxy-groups": [], "rules": []}, CUSTOMIZE)
    check(info["overlay"] is False, "无 select 组不叠加")


def test_name_dedup() -> None:
    print("新组名遇冲突自动加后缀")
    import copy
    base = copy.deepcopy(BASE)
    base["proxy-groups"].append({"name": "AI", "type": "select", "proxies": ["HK-01"]})
    config, info = overlay.apply(base, {"ai_domain_suffixes": ["openai.com"]})
    check("AI-1" in info["overlay_groups"], "AI 重名 → AI-1")


if __name__ == "__main__":
    for t in (test_overlay_apply, test_no_main_group, test_name_dedup):
        t()
    print(f"\n{'全部通过' if _failures == 0 else f'{_failures} 项失败'}")
    sys.exit(1 if _failures else 0)
