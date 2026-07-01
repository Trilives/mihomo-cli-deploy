"""命名订阅管理：增 / 删 / 改名 / 切换 active / 刷新 / 列表。

每个订阅存于 state/subscriptions/<name>/：meta.json + raw.* + config.yaml。
active 指针（state/active）决定哪份部署生效；切换会同步 state/config.yaml 并重启服务。

mihomo 直用机场订阅：clash/mihomo 来源经 patch 最小改写即可；base64 来源先经
subconverter 转 Clash 再 patch。自定义分流叠加（overlay）为可选，默认关闭。
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from .. import customize, paths, service, shell, yamlmini
from . import detect, fetch, patch

_EXT = {"clash": "yaml", "base64": "txt"}


@dataclass
class Subscription:
    name: str
    url: str
    source_type: str
    apply_overlay: bool = False
    created_at: str = ""
    updated_at: str = ""
    last_node_count: int = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(name: str) -> str:
    name = name.strip().replace("/", "-").replace("\\", "-").replace("..", "-")
    name = "-".join(name.split())  # 折叠空白
    return name.strip(". ") or "sub"


def _dir(name: str):
    return paths.subscription_dir(name)


def _meta_file(name: str):
    return _dir(name) / "meta.json"


def _config_file(name: str):
    return _dir(name) / "config.yaml"


# --------------------------------------------------------------------------- #
# 读取
# --------------------------------------------------------------------------- #
def list_all() -> "list[Subscription]":
    subs: list[Subscription] = []
    if not paths.SUBSCRIPTIONS_DIR.exists():
        return subs
    for d in sorted(paths.SUBSCRIPTIONS_DIR.iterdir()):
        meta = d / "meta.json"
        if meta.exists():
            try:
                subs.append(Subscription(**json.loads(meta.read_text("utf-8"))))
            except (json.JSONDecodeError, TypeError, OSError):
                continue
    return subs


def get(name: str) -> "Subscription | None":
    f = _meta_file(name)
    if not f.exists():
        return None
    try:
        return Subscription(**json.loads(f.read_text("utf-8")))
    except (json.JSONDecodeError, TypeError, OSError):
        return None


def get_active() -> "Subscription | None":
    if not paths.ACTIVE_FILE.exists():
        return None
    return get(paths.ACTIVE_FILE.read_text("utf-8").strip())


# --------------------------------------------------------------------------- #
# 增 / 改
# --------------------------------------------------------------------------- #
def add(name: str, url: str, source_type: str, *, apply_overlay: bool = False, set_active: bool = True) -> Subscription:
    name = _slug(name)
    if _meta_file(name).exists():
        raise RuntimeError(f"订阅「{name}」已存在，请改名或先删除。")
    sub = Subscription(
        name=name, url=url, source_type=source_type, apply_overlay=apply_overlay,
        created_at=_now(), updated_at=_now(),
    )
    _build(sub)
    if set_active:
        _apply_active(name)
    return sub


def refresh(name: str) -> Subscription:
    """联网重新拉取订阅原文并重建（用于「刷新订阅」/ 定时更新）。"""
    sub = get(name)
    if sub is None:
        raise RuntimeError(f"订阅不存在: {name}")
    sub.updated_at = _now()
    _build(sub)
    if get_active() and get_active().name == name:  # type: ignore[union-attr]
        _apply_active(name)
    return sub


def rebuild(name: str) -> Subscription:
    """基于本地已存订阅原文重新生成（不联网），用于应用定制层 / 叠加层等本地改动。

    订阅链接一般只在「刷新」时才重拉；改定制层只需把本地原文按新设置重建即可。
    本地无原文（异常情况）时回退为联网刷新。
    """
    sub = get(name)
    if sub is None:
        raise RuntimeError(f"订阅不存在: {name}")
    raw_file = _raw_file(sub)
    if not raw_file.exists():
        shell.warn("本地缺少订阅原文，改为联网刷新。")
        return refresh(name)
    sub.updated_at = _now()
    shell.info(f"用本地原文重新生成「{sub.name}」（不重新拉取）…")
    _convert_and_write(sub, raw_file.read_bytes(), customize.load())
    if get_active() and get_active().name == name:  # type: ignore[union-attr]
        _apply_active(name)
    return sub


def _raw_file(sub: Subscription):
    return _dir(sub.name) / f"raw.{_EXT.get(sub.source_type, 'txt')}"


def _build(sub: Subscription) -> None:
    """拉取 → 写 raw → 生成配置写盘。"""
    cfg = customize.load()
    proxy = str(cfg.get("download_proxy") or "")
    shell.info(f"拉取订阅「{sub.name}」…")
    raw = fetch.fetch(sub.url, source_type=sub.source_type, proxy=proxy)

    mismatch = detect.warn_if_mismatch(sub.source_type, raw)
    if mismatch:
        shell.warn(mismatch)

    _dir(sub.name).mkdir(parents=True, exist_ok=True)
    _raw_file(sub).write_bytes(raw)
    _convert_and_write(sub, raw, cfg)


def _convert_and_write(sub: Subscription, raw: bytes, cfg: dict) -> None:
    """把订阅原文生成 mihomo 配置（直用订阅 + 最小改写），写 config.yaml/meta。"""
    text = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else raw

    if sub.source_type == "base64":
        from . import b64
        shell.info("经 subconverter 将 base64 转为 Clash…")
        clash = b64.to_clash_dict(text, cfg)
    else:
        clash = yamlmini.load(text)
        if not isinstance(clash, dict):
            raise patch.PatchError("订阅 YAML 解析失败或根不是映射。")

    shell.info("生成 mihomo 配置（直用订阅 + 最小改写）…")
    config, info = patch.build(clash, cfg)

    if sub.apply_overlay:
        from . import overlay
        shell.info("叠加自定义分流（overlay）…")
        config, ov_info = overlay.apply(config, cfg)
        info.update(ov_info)

    # 地区自动测速聚合组：各地区独立开关，不依赖 overlay / apply_overlay
    if cfg.get("generate_sg_groups") or cfg.get("generate_hk_groups"):
        from . import regiongroups
        config, rg_info = regiongroups.apply(config, cfg)
        info.update(rg_info)
        if rg_info.get("region_groups"):
            shell.info("已生成地区自动测速聚合组：" + ", ".join(rg_info["region_groups"]))
        else:
            shell.warn("启用了地区聚合组，但未匹配到对应地区节点（检查关键词与开关）。")

    sub.last_node_count = int(info.get("proxies", 0) or 0)

    # mihomo 吃 Clash YAML；JSON 内容亦为合法 YAML（见 ARCHITECTURE.md §5）
    _config_file(sub.name).write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", "utf-8")
    _meta_file(sub.name).write_text(json.dumps(asdict(sub), ensure_ascii=False, indent=2) + "\n", "utf-8")
    shell.ok(
        f"订阅「{sub.name}」就绪：{info.get('proxies', 0)} 节点 / "
        f"{info.get('proxy_groups', 0)} 策略组 / {info.get('rules', 0)} 规则"
    )


# --------------------------------------------------------------------------- #
# 切换 / 删除 / 改名
# --------------------------------------------------------------------------- #
def switch(name: str) -> None:
    if not _meta_file(name).exists():
        raise RuntimeError(f"订阅不存在: {name}")
    _apply_active(name)
    shell.ok(f"已切换生效订阅: {name}")


def _apply_active(name: str) -> None:
    paths.ensure_state_dirs()
    shutil.copyfile(_config_file(name), paths.CONFIG_FILE)
    paths.ACTIVE_FILE.write_text(name + "\n", "utf-8")
    if service.is_installed():
        try:
            service.sync_and_restart()
        except (RuntimeError, shell.CommandError) as exc:
            shell.warn(f"配置已切换，但同步到服务失败：{exc}")


def remove(name: str) -> None:
    d = _dir(name)
    if not d.exists():
        raise RuntimeError(f"订阅不存在: {name}")
    was_active = get_active() and get_active().name == name  # type: ignore[union-attr]
    shutil.rmtree(d, ignore_errors=True)
    if was_active:
        paths.ACTIVE_FILE.unlink(missing_ok=True)
        shell.warn("已删除当前生效订阅；请切换到其它订阅或重新添加。")
    shell.ok(f"已删除订阅: {name}")


def rename(old: str, new: str) -> None:
    new = _slug(new)
    if not _meta_file(old).exists():
        raise RuntimeError(f"订阅不存在: {old}")
    if _meta_file(new).exists():
        raise RuntimeError(f"目标名已存在: {new}")
    _dir(old).rename(_dir(new))
    sub = get(new)
    if sub:
        sub.name = new
        sub.updated_at = _now()
        _meta_file(new).write_text(json.dumps(asdict(sub), ensure_ascii=False, indent=2) + "\n", "utf-8")
    if get_active() and get_active().name == old:  # type: ignore[union-attr]
        paths.ACTIVE_FILE.write_text(new + "\n", "utf-8")
    shell.ok(f"已改名: {old} → {new}")
