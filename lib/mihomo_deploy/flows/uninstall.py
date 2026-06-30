from __future__ import annotations

import shutil

from .. import menu, paths, resilience, service, shell, timer


def run() -> None:
    items = [
        "systemd 服务",
        "网络自愈（NM 钩子 + watchdog）",
        "每周更新定时器",
        "清理产物（内核 / UI / 下载缓存 / geo）",
        "清理所有订阅与配置（state/）",
    ]
    chosen = menu.multiselect("卸载（勾选要移除的项）", items, default_on=(0, 1, 2))
    if not chosen or not menu.confirm("确认执行？", default=False):
        return
    actions = [_svc, _resilience, _timer, _artifacts, _state]
    for idx in chosen:
        try:
            actions[idx]()
        except (RuntimeError, shell.CommandError) as exc:
            shell.error(f"移除失败：{exc}")
    shell.ok("卸载流程结束")


def _svc() -> None:
    service.remove(purge_runtime=True)


def _timer() -> None:
    timer.remove()


def _resilience() -> None:
    resilience.remove()


def _artifacts() -> None:
    for d in (paths.BIN_DIR, paths.UI_DIR, paths.DOWNLOADS_DIR, paths.GEO_DIR):
        shutil.rmtree(d, ignore_errors=True)
    for p in (paths.LEGACY_MIHOMO_BIN, paths.LEGACY_VERSION_FILE, paths.LEGACY_UI_DIR, paths.LEGACY_COUNTRY_MMDB, paths.LEGACY_GEOIP_METADB):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        else:
            p.unlink(missing_ok=True)
    shell.ok("已清理本地产物")


def _state() -> None:
    from .. import proxyenv
    proxyenv.remove()
    shutil.rmtree(paths.STATE_DIR, ignore_errors=True)
    paths.LEGACY_CONFIG_FILE.unlink(missing_ok=True)
    shell.ok("已清理 state/")
