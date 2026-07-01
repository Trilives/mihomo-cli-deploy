"""regiongroups（独立地区自动测速聚合组）单元测试。

运行： python3 tests/test_regiongroups.py
仅依赖标准库与本项目，不需要 mihomo 内核或网络。
"""

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from mihomo_deploy.subscription import regiongroups  # noqa: E402

BASE = {
    "proxies": [
        {"name": "🇭🇰 HK-01", "type": "ss"},
        {"name": "🇭🇰 HK-02", "type": "ss"},
        {"name": "🇸🇬 SG-01", "type": "ss"},
        {"name": "🇺🇸 US-01", "type": "ss"},
    ],
    "proxy-groups": [
        {"name": "Proxies", "type": "select",
         "proxies": ["🇭🇰 HK-01", "🇭🇰 HK-02", "🇸🇬 SG-01", "🇺🇸 US-01", "DIRECT"]},
    ],
    "rules": ["GEOIP,CN,DIRECT", "MATCH,Proxies"],
}

CUSTOMIZE = {
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


def test_apply_inserts_into_main() -> None:
    print("生成聚合组并插入主选择组前部")
    config, info = regiongroups.apply(copy.deepcopy(BASE), CUSTOMIZE)
    check(info["region_groups"] == ["SG-Auto", "HK-Auto"], "返回两个聚合组名")
    groups = {g["name"]: g for g in config["proxy-groups"]}
    check("SG-Auto" in groups and "HK-Auto" in groups, "聚合组已加入 proxy-groups")
    hk = groups["HK-Auto"]
    check(hk["type"] == "url-test", "HK-Auto 为 url-test（自动测速）")
    check(hk["proxies"] == ["🇭🇰 HK-01", "🇭🇰 HK-02"], "HK-Auto 按关键词聚合两个香港节点")
    main = groups["Proxies"]
    check(main["proxies"][:2] == ["SG-Auto", "HK-Auto"], "聚合组插到主选择组最前，可直接选用")
    check("🇺🇸 US-01" in main["proxies"], "主选择组原有节点保留")


def test_disabled_region_noop() -> None:
    print("未开任何地区 → 不建组")
    config, info = regiongroups.apply(copy.deepcopy(BASE), {})
    check(info["region_groups"] == [], "无地区开启时不建组")
    names = [g["name"] for g in config["proxy-groups"]]
    check(names == ["Proxies"], "proxy-groups 不变")


def test_no_match_skipped() -> None:
    print("地区开启但无匹配节点 → 跳过该地区")
    cz = {"generate_sg_groups": True, "prefer_keywords": ["不存在的地区"]}
    config, info = regiongroups.apply(copy.deepcopy(BASE), cz)
    check(info["region_groups"] == [], "无命中节点不建组")


def test_idempotent_reuse() -> None:
    print("已存在同名 url-test 组 → 复用而非重复建")
    base = copy.deepcopy(BASE)
    base["proxy-groups"].append(
        {"name": "HK-Auto", "type": "url-test", "proxies": ["🇭🇰 HK-01"]}
    )
    config, info = regiongroups.apply(base, {"generate_hk_groups": True,
                                             "hk_prefer_keywords": ["HK"]})
    hk_groups = [g for g in config["proxy-groups"] if g["name"] == "HK-Auto"]
    check(len(hk_groups) == 1, "HK-Auto 不重复创建")
    check("HK-Auto" in info["region_groups"], "复用的组仍计入并插入主组")


if __name__ == "__main__":
    for t in (test_apply_inserts_into_main, test_disabled_region_noop,
              test_no_match_skipped, test_idempotent_reuse):
        t()
    print(f"\n{'全部通过' if _failures == 0 else f'{_failures} 项失败'}")
    sys.exit(1 if _failures else 0)
