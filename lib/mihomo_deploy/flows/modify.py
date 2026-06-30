from __future__ import annotations

from .. import core, customize, menu, paths, service, shell
from ..subscription import manager
from ..tx import Transaction
from . import common


OPTIONS = [
    "订阅管理（增 / 删 / 改名 / 切换 / 刷新）",
    "编辑 Mihomo 定制层",
    "切换 / 固定节点 ※即时",
    "更新 核心 / UI / geo ※即时",
    "服务设置 ※即时",
    "网络自愈设置 ※即时",
    "每周更新定时器 ※即时",
]


def run() -> None:
    with Transaction("更改配置") as session:
        for p in (paths.CONFIG_FILE, paths.ACTIVE_FILE, paths.CUSTOMIZE_FILE, paths.SUBSCRIPTIONS_DIR):
            session.snapshot(p)
        session.add_undo("同步服务到回退后的配置", _resync_service)
        while True:
            try:
                idx = menu.select("更改配置", OPTIONS, back_label="回退并退出", save_label="保存并退出")
            except menu.SaveExit:
                return
            try:
                [_subscriptions, _edit_customize, _node_select, _update_core, _service_settings, _resilience, _timer][idx]()
            except menu.Cancelled:
                continue


def _resync_service() -> None:
    if service.is_installed() and manager.get_active():
        try:
            service.sync_and_restart()
        except (RuntimeError, shell.CommandError) as exc:
            shell.warn(f"服务同步失败：{exc}")


def _subscriptions() -> None:
    while True:
        subs = manager.list_all()
        active = manager.get_active()
        shell.header("订阅管理")
        for sub in subs:
            marker = " ← 生效" if active and active.name == sub.name else ""
            print(f"  - {sub.name} [{sub.source_type}, {sub.last_node_count} 节点]{marker}")
        try:
            act = menu.select("订阅操作", ["添加订阅", "切换生效订阅", "刷新订阅", "重命名", "删除订阅"], back_label="返回")
        except menu.Cancelled:
            return
        [_sub_add, _sub_switch, _sub_refresh, _sub_rename, _sub_remove][act]()


def _maybe_node_select() -> None:
    """订阅链接变化后，提示是否进入「切换 / 固定节点」（主菜单第③项）。"""
    if menu.confirm("订阅已更新，是否现在切换 / 固定节点？", default=False):
        _node_select()


def _sub_add() -> None:
    info = common.ask_new_subscription()
    if info is None:
        return
    name, url, source_type, customize_flag = info
    set_active = manager.get_active() is None or menu.confirm("设为生效订阅？", default=True)
    manager.add(name, url, source_type, customize_flag=customize_flag, set_active=set_active)
    if set_active:
        _maybe_node_select()


def _pick_sub(title: str) -> str | None:
    subs = manager.list_all()
    if not subs:
        shell.warn("暂无订阅")
        return None
    idx = menu.select(title, [s.name for s in subs])
    return subs[idx].name


def _sub_switch() -> None:
    name = _pick_sub("切换到哪个订阅")
    if name:
        manager.switch(name)
        _maybe_node_select()


def _sub_refresh() -> None:
    name = _pick_sub("刷新哪个订阅")
    if name:
        active = manager.get_active()
        manager.refresh(name)
        if active and active.name == name:
            _maybe_node_select()


def _sub_rename() -> None:
    name = _pick_sub("重命名哪个订阅")
    if name:
        manager.rename(name, menu.ask("新名称", allow_empty=False))


def _sub_remove() -> None:
    name = _pick_sub("删除哪个订阅")
    if name and menu.confirm(f"确认删除「{name}」？", default=False):
        manager.remove(name)


def _edit_customize() -> None:
    changed = customize.edit()
    active = manager.get_active()
    if changed and active and menu.confirm("立即重新生成当前订阅并同步服务？", default=True):
        manager.rebuild(active.name)


def _update_core() -> None:
    variant = "compatible" if menu.confirm("使用 compatible 内核构建？", default=False) else "standard"
    core.download_all(variant=variant, force=True)
    if manager.get_active() and service.is_installed():
        service.sync_and_restart()


def _node_select() -> None:
    from .. import node_select
    node_select.select(str(paths.CONFIG_FILE))


def _service_settings() -> None:
    idx = menu.select("服务设置", ["安装/重装服务", "查看状态", "同步当前配置并重启", "删除服务"], back_label="返回")
    if idx == 0:
        service.install(start=menu.confirm("现在启动服务？", default=True))
    elif idx == 1:
        service.status()
    elif idx == 2:
        service.sync_and_restart()
    else:
        service.remove()


def _timer() -> None:
    from .. import timer
    timer.menu_flow()


def _resilience() -> None:
    from .. import resilience
    resilience.menu_flow()
