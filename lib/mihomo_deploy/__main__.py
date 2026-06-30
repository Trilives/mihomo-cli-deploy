"""主入口：交互式主菜单分发到三大流程。

由 mihomo.sh 经 `python3 -m mihomo_deploy` 调起；也可带子命令直达，便于脚本化：
    python3 -m mihomo_deploy init|modify|uninstall
"""

from __future__ import annotations

import sys

from . import service, shell
from .flows import init, modify, nettest, uninstall
from .menu import Cancelled, select

def _update() -> None:
    """非交互更新：内核/UI/规则集 + 同步重启服务。供每周定时器调用。"""
    from . import core, service
    from .subscription import manager

    core.download_all(force=True)
    if manager.get_active() and service.is_installed():
        service.sync_and_restart()


_FLOWS = {
    "init": init.run,
    "modify": modify.run,
    "nettest": nettest.run,
    "uninstall": uninstall.run,
    "update": _update,
    "pause": service.pause,
    "resume": service.resume,
}


def _switch_label() -> str:
    """主菜单服务开关项标签：随主服务当前状态变化。"""
    if not service.is_installed():
        return "暂停 / 启动服务"
    return "暂停服务 ⏸" if service.is_active() else "启动服务 ▶"


def _interactive() -> int:
    while True:
        options = ["初始化（首次部署）", "更改配置", _switch_label(), "网络测试", "卸载所有服务"]
        actions = [init.run, modify.run, service.toggle_flow, nettest.run, uninstall.run]
        try:
            idx = select("mihomo 部署系统", options, back_label="退出")
        except Cancelled:
            print("再见。")
            return 0
        try:
            actions[idx]()
        except Cancelled:
            continue
        except KeyboardInterrupt:
            print()
            continue


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        cmd = argv[0]
        if cmd in ("-h", "--help", "help"):
            print("用法: mihomo.sh [init|modify|uninstall|update|pause|resume]")
            print("不带参数则进入交互式主菜单。")
            return 0
        fn = _FLOWS.get(cmd)
        if fn is None:
            shell.error(f"未知子命令: {cmd}")
            return 2
        try:
            fn()
        except Cancelled:
            pass
        return 0
    return _interactive()


if __name__ == "__main__":
    raise SystemExit(main())
