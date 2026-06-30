"""命名订阅管理：增 / 删 / 改名 / 切换 / 刷新。"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .. import customize, paths, service, shell, yamlmini
from . import fetch


@dataclass
class Subscription:
    name: str
    url: str
    source_type: str = "clash"
    customize: bool = False
    converter: str = "direct"
    created_at: str = ""
    updated_at: str = ""
    last_node_count: int = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(name: str) -> str:
    cleaned = name.strip().replace("/", "-").replace("\\", "-").replace("..", "-")
    cleaned = "-".join(cleaned.split())
    return cleaned.strip(". ") or "sub"


def _dir(name: str) -> Path:
    return paths.subscription_dir(name)


def _meta_file(name: str) -> Path:
    return _dir(name) / "meta.json"


def _raw_file(name: str) -> Path:
    return _dir(name) / "raw.yaml"


def _config_file(name: str) -> Path:
    return _dir(name) / "config.yaml"


def list_all() -> list[Subscription]:
    if not paths.SUBSCRIPTIONS_DIR.exists():
        return []
    out: list[Subscription] = []
    for d in sorted(paths.SUBSCRIPTIONS_DIR.iterdir()):
        meta = d / "meta.json"
        if not meta.exists():
            continue
        try:
            out.append(Subscription(**json.loads(meta.read_text("utf-8"))))
        except (json.JSONDecodeError, TypeError, OSError):
            continue
    return out


def get(name: str) -> Subscription | None:
    f = _meta_file(name)
    if not f.exists():
        return None
    try:
        return Subscription(**json.loads(f.read_text("utf-8")))
    except (json.JSONDecodeError, TypeError, OSError):
        return None


def get_active() -> Subscription | None:
    if not paths.ACTIVE_FILE.exists():
        return None
    return get(paths.ACTIVE_FILE.read_text("utf-8").strip())


def add(name: str, url: str, source_type: str, *, customize_flag: bool = False, set_active: bool = True) -> Subscription:
    paths.ensure_state_dirs()
    slug = _slug(name)
    if _meta_file(slug).exists():
        raise RuntimeError(f"订阅已存在: {slug}")
    sub = Subscription(
        name=slug,
        url=url,
        source_type=source_type,
        customize=customize_flag,
        created_at=_now(),
        updated_at=_now(),
    )
    _build(sub, from_network=True)
    if set_active:
        _apply_active(slug)
    return sub


def refresh(name: str) -> Subscription:
    sub = get(name)
    if sub is None:
        raise RuntimeError(f"订阅不存在: {name}")
    sub.updated_at = _now()
    _build(sub, from_network=True)
    if get_active() and get_active().name == name:  # type: ignore[union-attr]
        _apply_active(name)
    return sub


def rebuild(name: str) -> Subscription:
    sub = get(name)
    if sub is None:
        raise RuntimeError(f"订阅不存在: {name}")
    if not _raw_file(name).exists():
        return refresh(name)
    sub.updated_at = _now()
    _write_config(sub, _raw_file(name).read_bytes())
    if get_active() and get_active().name == name:  # type: ignore[union-attr]
        _apply_active(name)
    return sub


def _build(sub: Subscription, *, from_network: bool) -> None:
    cfg = customize.load()
    proxy = str(cfg.get("download_proxy") or "")
    if from_network:
        shell.info(f"拉取订阅「{sub.name}」...")
        if sub.source_type == "base64":
            raw = fetch.converted(
                sub.url,
                backend=str(cfg.get("subconverter_backend") or "https://api.v1.mk"),
                proxy=proxy,
                extra_params=[str(x) for x in cfg.get("subconverter_extra_params", [])],
            )
            sub.converter = "subconverter"
        else:
            raw = fetch.direct(sub.url, proxy=proxy)
            sub.converter = "direct"
        _dir(sub.name).mkdir(parents=True, exist_ok=True)
        _raw_file(sub.name).write_bytes(raw)
    else:
        raw = _raw_file(sub.name).read_bytes()
    _write_config(sub, raw)


def _write_config(sub: Subscription, raw: bytes) -> None:
    _dir(sub.name).mkdir(parents=True, exist_ok=True)
    config_path = _config_file(sub.name)
    config_path.write_bytes(raw if raw.endswith(b"\n") else raw + b"\n")
    if sub.customize:
        try:
            if customize.add_region_groups(config_path):
                shell.ok("已追加 SG/HK 定制分组")
        except Exception as exc:
            shell.warn(f"定制分组生成失败，保留订阅原分组：{exc}")
    sub.last_node_count = _count_nodes(config_path)
    _meta_file(sub.name).write_text(json.dumps(asdict(sub), ensure_ascii=False, indent=2) + "\n", "utf-8")
    shell.ok(f"订阅「{sub.name}」就绪：{sub.last_node_count} 节点")


def _count_nodes(config_path: Path) -> int:
    try:
        data = yamlmini.load(config_path.read_text("utf-8"))
    except Exception:
        return 0
    proxies = data.get("proxies") if isinstance(data, dict) else None
    return len(proxies) if isinstance(proxies, list) else 0


def switch(name: str) -> None:
    if not _config_file(name).exists():
        raise RuntimeError(f"订阅不存在: {name}")
    _apply_active(name)
    shell.ok(f"已切换生效订阅: {name}")


def _apply_active(name: str) -> None:
    paths.ensure_state_dirs()
    shutil.copyfile(_config_file(name), paths.CONFIG_FILE)
    paths.ACTIVE_FILE.write_text(name + "\n", "utf-8")
    shutil.copyfile(paths.CONFIG_FILE, paths.LEGACY_CONFIG_FILE)
    if service.is_installed():
        try:
            service.sync_and_restart()
        except (RuntimeError, shell.CommandError) as exc:
            shell.warn(f"配置已切换，但同步服务失败：{exc}")


def remove(name: str) -> None:
    if not _dir(name).exists():
        raise RuntimeError(f"订阅不存在: {name}")
    active = get_active()
    shutil.rmtree(_dir(name), ignore_errors=True)
    if active and active.name == name:
        paths.ACTIVE_FILE.unlink(missing_ok=True)
        paths.CONFIG_FILE.unlink(missing_ok=True)
        paths.LEGACY_CONFIG_FILE.unlink(missing_ok=True)
    shell.ok(f"已删除订阅: {name}")


def rename(old: str, new: str) -> None:
    new_slug = _slug(new)
    if not _dir(old).exists():
        raise RuntimeError(f"订阅不存在: {old}")
    if _dir(new_slug).exists():
        raise RuntimeError(f"目标订阅已存在: {new_slug}")
    _dir(old).rename(_dir(new_slug))
    sub = get(new_slug)
    if sub:
        sub.name = new_slug
        sub.updated_at = _now()
        _meta_file(new_slug).write_text(json.dumps(asdict(sub), ensure_ascii=False, indent=2) + "\n", "utf-8")
    active = get_active()
    if active and active.name == old:
        paths.ACTIVE_FILE.write_text(new_slug + "\n", "utf-8")
    shell.ok(f"已重命名: {old} -> {new_slug}")
