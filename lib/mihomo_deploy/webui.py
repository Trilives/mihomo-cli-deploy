"""独立 Web 面板服务（可选）：把已下载的面板托管在**根路径**，浏览器打开根地址即用。

mihomo 自带的 external-ui 只挂在控制器的 `/ui` 子路径（须 http://IP:9090/ui/）；这是 mihomo
与 sing-box 的固有差异。本模块用一个极简静态服务（python3 -m http.server）把同一份面板挂在
独立端口的**根路径**，并把面板 config.js 的 defaultBackendURL 指向控制器，实现「打开根地址即
用」（体验与 sing-box 一致）。

依赖控制器已开启 CORS（Clash API 默认允许跨源），故面板端口与控制器 9090 跨端口通信可用。
面板文件单独暂存到 /etc/mihomo/webui（与 mihomo 服务的 /etc/mihomo/ui 互不影响），保持自包含。

作为 systemd 服务 mihomo-webui.service 管理；安装/卸载方式与 resilience / timer 一致。
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import paths, shell

WEBUI_NAME = "mihomo-webui"
DEFAULT_PORT = 9091
CONTROLLER_PORT = 9090
# 独立面板专用暂存目录（不与 mihomo 服务的 external-ui 目录共用，卸载时可安全清理）
_RUNTIME_UI = paths.ETC_DIR / "webui"


def _unit() -> Path:
    return Path(f"/etc/systemd/system/{WEBUI_NAME}.service")


def is_installed() -> bool:
    return _unit().exists()


def _python_bin() -> str:
    return sys.executable or "/usr/bin/python3"


def _config_js(backend_url: str) -> str:
    return (
        "window.__METACUBEXD_CONFIG__ = {\n"
        f"  defaultBackendURL: '{backend_url}',\n"
        "}\n"
    )


def configure_backend(backend_url: str) -> None:
    """把面板 config.js 的 defaultBackendURL 写到源 state/ui，供托管时自动连后端。"""
    if paths.UI_DIR.exists():
        (paths.UI_DIR / "config.js").write_text(_config_js(backend_url), "utf-8")


def _default_backend(lan: bool) -> str:
    # 本机/SSH 隧道场景直连本地控制器；LAN 场景浏览器在远端，留空让用户首次输入 服务器IP:9090
    return "" if lan else f"http://127.0.0.1:{CONTROLLER_PORT}"


def _unit_text(port: int, host: str, ui_dir: Path, py: str) -> str:
    return f"""[Unit]
Description=mihomo Web UI static server (root-path panel, {WEBUI_NAME})
After=network-online.target mihomo.service
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart={py} -m http.server {port} --bind {host} --directory {ui_dir}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
"""


def install(*, port: int = DEFAULT_PORT, lan: bool = False, backend_url: str | None = None) -> None:
    """安装/重装独立面板服务并启动。需先下载 Web UI。"""
    if not shell._have("systemctl"):
        raise RuntimeError("未找到 systemctl，独立面板服务需要 systemd。")
    if not (paths.UI_DIR / "index.html").exists():
        raise RuntimeError("未找到 Web UI，请先执行『下载内核 / UI / geo 数据』或在初始化时选择下载面板。")

    host = "0.0.0.0" if lan else "127.0.0.1"
    if backend_url is None:
        backend_url = _default_backend(lan)

    shell.ensure_sudo("安装独立 Web 面板服务")
    configure_backend(backend_url)
    shell.run_root(["mkdir", "-p", str(paths.ETC_DIR)])
    shell.run_root(["rm", "-rf", str(_RUNTIME_UI)])
    shell.run_root(["cp", "-a", str(paths.UI_DIR), str(_RUNTIME_UI)])

    shell.write_root(_unit(), _unit_text(port, host, _RUNTIME_UI, _python_bin()))
    shell.run_root(["systemctl", "daemon-reload"])
    shell.run_root(["systemctl", "enable", "--now", f"{WEBUI_NAME}.service"])
    disp = host if lan else "127.0.0.1"
    shell.ok(f"独立 Web 面板已启动：http://{disp}:{port}/")
    if lan and not backend_url:
        shell.info(f"首次打开请在面板里填后端地址 http://<服务器IP>:{CONTROLLER_PORT}（如设了 secret 一并填）。")


def remove() -> None:
    shell.ensure_sudo("卸载独立 Web 面板服务")
    shell.run_root(["systemctl", "stop", f"{WEBUI_NAME}.service"], check=False, capture=True)
    shell.run_root(["systemctl", "disable", f"{WEBUI_NAME}.service"], check=False, capture=True)
    shell.run_root(["rm", "-f", str(_unit())], check=False)
    shell.run_root(["rm", "-rf", str(_RUNTIME_UI)], check=False)
    shell.run_root(["systemctl", "daemon-reload"], check=False)
    shell.ok("独立 Web 面板已卸载。")


def refresh() -> None:
    """UI 更新后用现有端口/绑定重新暂存并重启（保持 config.js 后端设置）。"""
    if not is_installed():
        return
    from . import customize
    cfg = customize.load()
    install(port=int(cfg.get("webui_port") or DEFAULT_PORT), lan=bool(cfg.get("lan_panel")))


# --------------------------------------------------------------------------- #
# 交互
# --------------------------------------------------------------------------- #
def setup_interactive(*, default_port: int | None = None, lan: bool = False) -> int | None:
    """交互式安装/重配独立面板。返回最终端口（取消则 None）。"""
    from . import customize, firewall, menu

    cfg = customize.load()
    port = int(default_port or cfg.get("webui_port") or DEFAULT_PORT)
    raw = menu.ask("独立面板端口", default=str(port))
    try:
        port = int(raw)
    except ValueError:
        shell.warn("端口需为整数，已取消。")
        return None

    install(port=port, lan=lan)
    cfg["webui_port"] = port
    customize.save(cfg)
    if lan and menu.confirm(f"更新防火墙放行 {port} 端口？", default=True):
        firewall.allow(port)
    return port


def menu_flow() -> None:
    from . import customize, menu

    installed = is_installed()
    status = "已安装" if installed else "未安装"
    opts = (["重新配置 / 换端口", "卸载独立面板"] if installed
            else ["安装独立面板（根路径直接打开）"])
    try:
        idx = menu.select(f"独立 Web 面板（当前：{status}）", opts)
    except menu.Cancelled:
        return
    if installed and idx == 1:
        remove()
        return
    lan = bool(customize.load().get("lan_panel"))
    setup_interactive(lan=lan)


def run(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="mihomo_deploy.webui")
    p.add_argument("action", choices=["install", "remove", "refresh"])
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--lan", action="store_true")
    args = p.parse_args(argv)
    try:
        if args.action == "install":
            install(port=args.port, lan=args.lan)
        elif args.action == "refresh":
            refresh()
        else:
            remove()
    except (RuntimeError, shell.CommandError) as exc:
        shell.error(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
