"""Mihomo 定制层：dashboard、TUN、局域网代理和地区组增强。"""

from __future__ import annotations

import json
import re
import secrets
from copy import deepcopy
from pathlib import Path
from typing import Any

from . import menu, paths, shell, yamlmini

DEFAULTS: dict[str, Any] = {
    "download_proxy": "",
    "github_mirror": "",
    "allow_lan": False,
    "lan_panel": False,
    "enable_tun": True,
    "tun_stack": "gvisor",
    "external_ui": "ui",
    "external_controller": "127.0.0.1:9090",
    "generate_secret": True,
    "generate_sg_groups": True,
    "generate_hk_groups": True,
    "sg_keywords": ["新加坡", "狮城", "Singapore", "SG"],
    "hk_keywords": ["香港", "Hong Kong", "HK"],
    "subconverter_backend": "https://api.v1.mk",
    "subconverter_extra_params": ["emoji=true", "udp=true"],
}


def load() -> dict[str, Any]:
    data: dict[str, Any] = {}
    if paths.CUSTOMIZE_FILE.exists():
        try:
            data = json.loads(paths.CUSTOMIZE_FILE.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    merged = deepcopy(DEFAULTS)
    merged.update(data)
    return merged


def save(cfg: dict[str, Any]) -> None:
    paths.ensure_state_dirs()
    merged = deepcopy(DEFAULTS)
    merged.update(cfg)
    paths.CUSTOMIZE_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _is_top_level_key(line: str) -> bool:
    return re.match(r"^[A-Za-z0-9_-]+\s*:", line) is not None


def _top_level_key(line: str) -> str | None:
    match = re.match(r"^([A-Za-z0-9_-]+)\s*:", line)
    return match.group(1) if match else None


def _find_block(lines: list[str], key: str) -> tuple[int, int] | None:
    start = next((i for i, line in enumerate(lines) if _top_level_key(line) == key), None)
    if start is None:
        return None
    end = start + 1
    while end < len(lines) and not _is_top_level_key(lines[end]):
        end += 1
    return start, end


def _default_insert_index(lines: list[str]) -> int:
    for idx, line in enumerate(lines):
        if _top_level_key(line) in {"sniffer", "dns", "tun", "proxies", "proxy-groups", "rules"}:
            return idx
    return len(lines)


def _replace_or_insert(lines: list[str], key: str, block: list[str], insert_at: int | None = None) -> list[str]:
    bounds = _find_block(lines, key)
    if bounds:
        start, end = bounds
        return lines[:start] + block + lines[end:]
    at = _default_insert_index(lines) if insert_at is None else insert_at
    return lines[:at] + block + lines[at:]


def _existing_value(lines: list[str], key: str) -> str | None:
    bounds = _find_block(lines, key)
    if not bounds:
        return None
    value = lines[bounds[0]].split(":", 1)[1].strip().strip("\"'")
    return value or None


def _quote(value: str) -> str:
    return '"' + value.replace('"', '\\"') + '"'


def _tun_block(stack: str) -> list[str]:
    return [
        "tun:",
        "  enable: true",
        f"  stack: {stack}",
        "  auto-route: true",
        "  auto-detect-interface: true",
        "  dns-hijack:",
        "    - any:53",
        "    - tcp://any:53",
    ]


def ensure_runtime_settings(config_path: Path, cfg: dict[str, Any] | None = None) -> None:
    """只编辑顶层 Mihomo 设置，避免解析/重写整份订阅 YAML。"""
    c = load() if cfg is None else cfg
    if not config_path.exists():
        raise RuntimeError(f"未找到配置文件: {config_path}")
    text = config_path.read_text("utf-8")
    trailing_newline = text.endswith("\n")
    lines = text.splitlines()

    controller = str(c.get("external_controller") or _existing_value(lines, "external-controller") or "127.0.0.1:9090")
    if c.get("lan_panel"):
        controller = "0.0.0.0:9090"
    secret = _existing_value(lines, "secret")
    if not secret and c.get("generate_secret"):
        secret = secrets.token_hex(16)

    top_values = [
        ("allow-lan", "true" if c.get("allow_lan") else "false"),
        ("external-controller", controller),
        ("external-ui", str(c.get("external_ui") or "ui")),
        ("mode", "Rule"),
    ]
    for key, value in top_values:
        lines = _replace_or_insert(lines, key, [f"{key}: {value}"])
    if secret:
        lines = _replace_or_insert(lines, "secret", [f"secret: {_quote(secret)}"])
    if c.get("enable_tun"):
        insert_at = next((i for i, line in enumerate(lines) if _top_level_key(line) in {"proxies", "proxy-groups", "rules"}), len(lines))
        lines = _replace_or_insert(lines, "tun", _tun_block(str(c.get("tun_stack") or "gvisor")), insert_at)

    updated = "\n".join(lines)
    if trailing_newline:
        updated += "\n"
    config_path.write_text(updated, "utf-8")


def _dump_scalar(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    if s == "" or any(ch in s for ch in [":", "#", "{", "}", "[", "]", ","]) or s.strip() != s:
        return _quote(s)
    return s


def _dump_yaml(value: Any, indent: int = 0) -> list[str]:
    pad = " " * indent
    if isinstance(value, dict):
        out: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                out.append(f"{pad}{key}:")
                out.extend(_dump_yaml(item, indent + 2))
            else:
                out.append(f"{pad}{key}: {_dump_scalar(item)}")
        return out
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, dict):
                out.append(f"{pad}-")
                out.extend(_dump_yaml(item, indent + 2))
            elif isinstance(item, list):
                out.append(f"{pad}-")
                out.extend(_dump_yaml(item, indent + 2))
            else:
                out.append(f"{pad}- {_dump_scalar(item)}")
        return out
    return [f"{pad}{_dump_scalar(value)}"]


def _contains_keyword(name: str, keywords: list[str]) -> bool:
    low = name.lower()
    return any(str(k).lower() in low for k in keywords)


def add_region_groups(config_path: Path, cfg: dict[str, Any] | None = None) -> bool:
    """解析 Clash YAML，追加 SG/HK url-test/fallback 组并重写 YAML。"""
    c = load() if cfg is None else cfg
    data = yamlmini.load(config_path.read_text("utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("配置不是 YAML mapping")
    proxies = data.get("proxies")
    groups = data.get("proxy-groups")
    if not isinstance(proxies, list) or not isinstance(groups, list):
        raise RuntimeError("配置缺少 proxies/proxy-groups，无法追加地区组")

    changed = False
    existing = {g.get("name") for g in groups if isinstance(g, dict)}

    def add_pair(prefix: str, keywords: list[str]) -> None:
        nonlocal changed
        names = [p.get("name") for p in proxies if isinstance(p, dict) and isinstance(p.get("name"), str) and _contains_keyword(p["name"], keywords)]
        names = [n for n in names if isinstance(n, str)]
        if not names:
            return
        auto_name = f"{prefix}-Auto"
        fallback_name = f"{prefix}-Fallback"
        new_groups = []
        if auto_name not in existing:
            new_groups.append({"name": auto_name, "type": "url-test", "proxies": names, "url": "http://www.gstatic.com/generate_204", "interval": 300})
        if fallback_name not in existing:
            new_groups.append({"name": fallback_name, "type": "fallback", "proxies": names, "url": "http://www.gstatic.com/generate_204", "interval": 300})
        if new_groups:
            groups[:0] = new_groups
            changed = True
            first_select = next((g for g in groups if isinstance(g, dict) and g.get("type") == "select" and isinstance(g.get("proxies"), list)), None)
            if first_select:
                for name in (fallback_name, auto_name):
                    if name not in first_select["proxies"]:
                        first_select["proxies"].insert(0, name)

    if c.get("generate_sg_groups"):
        add_pair("SG", [str(x) for x in c.get("sg_keywords", [])])
    if c.get("generate_hk_groups"):
        add_pair("HK", [str(x) for x in c.get("hk_keywords", [])])
    if changed:
        config_path.write_text("\n".join(_dump_yaml(data)) + "\n", "utf-8")
    return changed


def apply_all(config_path: Path, *, enhance_groups: bool = True) -> None:
    cfg = load()
    ensure_runtime_settings(config_path, cfg)
    if enhance_groups:
        try:
            if add_region_groups(config_path, cfg):
                shell.ok("已追加地区测速/故障切换分组")
        except Exception as exc:
            shell.warn(f"地区组增强跳过：{exc}")


# --------------------------------------------------------------------------- #
# 交互式编辑（缓冲式菜单；字段集为 Mihomo 自身配置，不含机场原生模式用不到的
# 分流 / DNS / 路由字段）
# --------------------------------------------------------------------------- #
_LIST_FIELDS = {
    "sg_keywords": "新加坡关键词",
    "hk_keywords": "香港关键词",
    "subconverter_extra_params": "subconverter 额外参数",
}
_BOOL_FIELDS = {
    "enable_tun": "TUN 模式（全局透明代理）",
    "allow_lan": "局域网代理 allow-lan",
    "lan_panel": "Web UI 暴露到 0.0.0.0",
    "generate_sg_groups": "生成新加坡地区组",
    "generate_hk_groups": "生成香港地区组",
    "generate_secret": "自动生成 Clash API secret",
}
_SCALAR_FIELDS = {
    "download_proxy": "下载代理",
    "subconverter_backend": "subconverter 后端",
    "github_mirror": "GitHub 加速前缀",
    "tun_stack": "TUN 协议栈（gvisor/system/mixed）",
    "external_controller": "Clash API 监听",
    "external_ui": "Web UI 目录",
}
# 编辑项展示顺序：常用项（TUN / 局域网 / 地区组 / 下载&转换后端）在前，
# 高级项（协议栈 / API 监听 / secret / 转换参数）在后。
_FIELD_ORDER = [
    "enable_tun",
    "allow_lan",
    "lan_panel",
    "generate_sg_groups",
    "generate_hk_groups",
    "download_proxy",
    "subconverter_backend",
    "github_mirror",
    "sg_keywords",
    "hk_keywords",
    "tun_stack",
    "external_controller",
    "external_ui",
    "generate_secret",
    "subconverter_extra_params",
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
    """交互式编辑 customize.json（缓冲式）。

    「保存并退出」才写盘；ESC = 放弃本次全部改动。返回是否实际保存了改动。
    """
    original = load()
    cfg = json.loads(json.dumps(original))  # 工作副本
    changed = False
    while True:
        try:
            idx = menu.select(
                "编辑 Mihomo 定制层", _edit_labels(cfg),
                back_label="放弃修改并退出", save_label="保存并退出",
            )
        except menu.SaveExit:
            if not changed:
                shell.info("未做修改。")
                return False
            save(cfg)
            shell.ok("定制层已保存。")
            _sync_lan_firewall(original, cfg)
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


def _sync_lan_firewall(original: dict[str, Any], cfg: dict[str, Any]) -> None:
    """allow_lan 开关变化时，按需更新防火墙放行 7890 端口。"""
    before, after = bool(original.get("allow_lan")), bool(cfg.get("allow_lan"))
    if before == after:
        return
    from . import firewall
    if after:
        if menu.confirm("已开启局域网代理，更新防火墙放行 7890 端口？", default=True):
            firewall.allow(firewall.PROXY_PORT)
    elif menu.confirm("已关闭局域网代理，撤销防火墙放行 7890 端口？", default=True):
        firewall.revoke(firewall.PROXY_PORT)


def _edit_list(cfg: dict[str, Any], key: str, label: str) -> bool:
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
                items.append(menu.ask("新增值", allow_empty=False))
            elif act == 1:
                if not items:
                    continue
                di = menu.select("删除哪一条", [str(x) for x in items])
                items.pop(di)
            elif act == 2:
                raw = menu.ask("粘贴（逗号或空格分隔）", allow_empty=True)
                items = [t for t in raw.replace(",", " ").split() if t]
            elif act == 3:
                items = list(DEFAULTS.get(key, []))
            elif act == 4:
                items = []
        except menu.Cancelled:
            continue
        cfg[key] = items
        changed = True


def _edit_scalar(cfg: dict[str, Any], key: str, label: str) -> bool:
    cur = str(cfg.get(key, "") or "")
    try:
        cfg[key] = menu.ask(f"{label}（留空清除）", default=cur, allow_empty=True)
    except menu.Cancelled:
        return False
    return True

