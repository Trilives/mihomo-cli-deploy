"""Mihomo 部署 CLI 主入口。"""

from __future__ import annotations

import sys

from . import core, service, shell
from .flows import init, modify, nettest, uninstall
from .menu import Cancelled, select
from .subscription import manager


def _update() -> None:
    core.download_all(force=True)
    if manager.get_active() and service.is_installed():
        service.sync_and_restart()


FLOWS = {
    "init": init.run,
    "modify": modify.run,
    "nettest": nettest.run,
    "uninstall": uninstall.run,
    "update": _update,
}


def _interactive() -> int:
    options = ["初始化（首次部署）", "更改配置", "网络测试", "卸载"]
    actions = [init.run, modify.run, nettest.run, uninstall.run]
    while True:
        try:
            idx = select("Mihomo 部署系统", options, back_label="退出")
        except Cancelled:
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
        if argv[0] in ("-h", "--help", "help"):
            print("用法: mihomo.sh [init|modify|nettest|uninstall|update]")
            return 0
        fn = FLOWS.get(argv[0])
        if fn is None:
            shell.error(f"未知子命令: {argv[0]}")
            return 2
        try:
            fn()
        except Cancelled:
            return 0
        return 0
    return _interactive()


if __name__ == "__main__":
    raise SystemExit(main())
