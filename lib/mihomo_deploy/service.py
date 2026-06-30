"""systemd 服务管理：暂存自包含 Mihomo 运行时到 /etc/mihomo。"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from . import customize, paths, shell

DEFAULT_NAME = "mihomo"
CONFLICTING_NAME = "sing-box"


def _runtime_paths(name: str) -> dict[str, Path]:
    d = paths.ETC_DIR
    return {
        "dir": d,
        "bin": d / "mihomo",
        "config": d / f"{name}.yaml",
        "cache": d / f"{name}.cache.db",
        "ui": d / "ui",
        "unit": Path(f"/etc/systemd/system/{name}.service"),
    }


def _preflight() -> None:
    if not paths.MIHOMO_BIN.exists():
        raise RuntimeError("未找到 mihomo 内核，请先执行更新核心/UI/geo。")
    if not paths.CONFIG_FILE.exists():
        raise RuntimeError("未找到生效配置 state/config.yaml，请先添加订阅。")
    if not shell._have("systemctl"):
        raise RuntimeError("未找到 systemctl，注册服务需要 systemd。")


def _stage_config() -> Path:
    tmp = Path(tempfile.mkstemp(prefix=".runtime-config.", suffix=".yaml", dir=paths.STATE_DIR)[1])
    shutil.copy2(paths.CONFIG_FILE, tmp)
    customize.ensure_runtime_settings(tmp)
    return tmp


def install(name: str = DEFAULT_NAME, *, start: bool = True) -> None:
    _preflight()
    rt = _runtime_paths(name)
    shell.ensure_sudo("注册系统服务")
    staged = _stage_config()
    try:
        shell.run_root(["mkdir", "-p", str(rt["dir"])], reason="创建运行时目录")
        shell.run_root(["chmod", "0755", str(rt["dir"])])
        shell.run_root(["install", "-m", "0755", str(paths.MIHOMO_BIN), str(rt["bin"]) + ".new"])
        shell.run_root(["mv", "-f", str(rt["bin"]) + ".new", str(rt["bin"])])
        shell.run_root(["install", "-m", "0644", str(staged), str(rt["config"])])
        shell.run_root(["install", "-m", "0644", "/dev/null", str(rt["cache"])])
        for geo in (paths.COUNTRY_MMDB, paths.GEOIP_METADB):
            if geo.exists():
                shell.run_root(["install", "-m", "0644", str(geo), str(rt["dir"] / geo.name)])
        if paths.UI_DIR.exists():
            shell.run_root(["rm", "-rf", str(rt["ui"])])
            shell.run_root(["cp", "-a", str(paths.UI_DIR), str(rt["ui"])])
        else:
            shell.warn("未找到 Web UI，面板将不可用。")
        shell.run_root([str(rt["bin"]), "-d", str(rt["dir"]), "-f", str(rt["config"]), "-t"], reason="校验配置")
    finally:
        staged.unlink(missing_ok=True)

    _remove_unit(name, quiet=True)
    if name != CONFLICTING_NAME:
        _remove_unit(CONFLICTING_NAME, quiet=True)

    unit_text = (paths.TEMPLATES_DIR / "mihomo.service.tmpl").read_text("utf-8").format(
        name=name,
        runtime_dir=str(rt["dir"]),
        bin=str(rt["bin"]),
        config=str(rt["config"]),
    )
    unit_tmp = Path(tempfile.mkstemp(prefix=".unit.", suffix=".service", dir=paths.STATE_DIR)[1])
    unit_tmp.write_text(unit_text, "utf-8")
    try:
        shell.run_root(["install", "-m", "0644", str(unit_tmp), str(rt["unit"])])
    finally:
        unit_tmp.unlink(missing_ok=True)
    shell.run_root(["systemctl", "daemon-reload"])
    shell.run_root(["systemctl", "enable", f"{name}.service"])
    if start:
        shell.run_root(["systemctl", "restart", f"{name}.service"])
        shell.ok(f"服务已启动: {name}.service")
    else:
        shell.ok(f"服务已设为开机自启（未启动）: {name}.service")


def sync_and_restart(name: str = DEFAULT_NAME) -> None:
    if not is_installed(name):
        shell.warn(f"服务 {name} 未安装，跳过同步。")
        return
    _preflight()
    rt = _runtime_paths(name)
    shell.ensure_sudo("更新服务配置")
    staged = _stage_config()
    try:
        shell.run_root(["install", "-m", "0644", str(staged), str(rt["config"])])
        shell.run_root([str(rt["bin"]), "-d", str(rt["dir"]), "-f", str(rt["config"]), "-t"], reason="校验配置")
    finally:
        staged.unlink(missing_ok=True)
    shell.run_root(["systemctl", "restart", f"{name}.service"])
    shell.ok(f"已同步配置并重启: {name}.service")


def remove(name: str = DEFAULT_NAME, *, purge_runtime: bool = True) -> None:
    shell.ensure_sudo("删除系统服务")
    _remove_unit(name)
    if purge_runtime:
        rt = _runtime_paths(name)
        shell.run_root(["rm", "-f", str(rt["config"]), str(rt["cache"])], check=False)
        remaining = shell.run_root(["bash", "-c", f"ls {paths.ETC_DIR}/*.yaml 2>/dev/null | wc -l"], check=False, capture=True)
        if (remaining.stdout or "0").strip() == "0":
            shell.run_root(["rm", "-rf", str(paths.ETC_DIR)], check=False)
    shell.ok(f"服务已删除: {name}.service")


def _remove_unit(name: str, *, quiet: bool = False) -> None:
    shell.run_root(["systemctl", "stop", f"{name}.service"], check=False, capture=quiet)
    shell.run_root(["systemctl", "disable", f"{name}.service"], check=False, capture=quiet)
    shell.run_root(["rm", "-f", f"/etc/systemd/system/{name}.service"], check=False)
    shell.run_root(["systemctl", "daemon-reload"], check=False, capture=quiet)
    shell.run_root(["systemctl", "reset-failed", f"{name}.service"], check=False, capture=quiet)


def is_installed(name: str = DEFAULT_NAME) -> bool:
    return _runtime_paths(name)["unit"].exists()


def status(name: str = DEFAULT_NAME) -> None:
    shell.run(["systemctl", "status", "--no-pager", f"{name}.service"], check=False)


def run(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="mihomo_deploy.service")
    p.add_argument("action", choices=["install", "remove", "sync", "status"])
    p.add_argument("-n", "--name", default=DEFAULT_NAME)
    p.add_argument("--no-start", action="store_true")
    args = p.parse_args(argv)
    try:
        if args.action == "install":
            install(args.name, start=not args.no_start)
        elif args.action == "remove":
            remove(args.name)
        elif args.action == "sync":
            sync_and_restart(args.name)
        else:
            status(args.name)
    except (RuntimeError, shell.CommandError) as exc:
        shell.error(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())

