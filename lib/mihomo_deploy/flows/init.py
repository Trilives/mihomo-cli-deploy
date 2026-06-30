from __future__ import annotations

from .. import core, customize, menu, paths, service, shell
from ..subscription import manager
from ..tx import Transaction
from . import common


def run() -> None:
    with Transaction("初始化") as tx:
        shell.header("初始化（首次部署）")
        cfg = customize.load()
        proxy = menu.ask("下载代理 IP:端口（留空直连）", default=common.strip_scheme(str(cfg.get("download_proxy") or "")))
        cfg["download_proxy"] = common.normalize_proxy(proxy)
        cfg["enable_tun"] = menu.confirm("启用 TUN？", default=bool(cfg.get("enable_tun")))
        cfg["allow_lan"] = menu.confirm("开启局域网代理 allow-lan？", default=bool(cfg.get("allow_lan")))
        cfg["lan_panel"] = menu.confirm("开放 Web UI 到局域网？", default=bool(cfg.get("lan_panel")))
        tx.backup_file(paths.CUSTOMIZE_FILE)
        customize.save(cfg)

        if not cfg["enable_tun"] and menu.confirm("把代理环境变量写入 ~/.bashrc？", default=True):
            from .. import proxyenv
            tx.backup_file(proxyenv.target_bashrc())
            proxyenv.write()

        if cfg["allow_lan"] and menu.confirm("更新防火墙放行 7890 端口？", default=True):
            from .. import firewall
            tx.add_undo("撤销防火墙放行 7890", lambda: firewall.revoke(firewall.PROXY_PORT))
            firewall.allow(firewall.PROXY_PORT)

        if menu.confirm("现在下载/更新 mihomo 核心、UI、geo？", default=True):
            variant = "compatible" if menu.confirm("使用 compatible 内核构建？", default=False) else "standard"
            core.download_all(variant=variant)

        info = common.ask_new_subscription()
        if info is None:
            shell.info("已跳过订阅和服务注册。稍后可用 `./mihomo.sh modify` 添加。")
            return
        name, url, source_type, customize_flag = info
        tx.backup_file(paths.CONFIG_FILE)
        tx.backup_file(paths.ACTIVE_FILE)
        sub = manager.add(name, url, source_type, customize_flag=customize_flag, set_active=True)
        tx.add_undo(f"删除订阅 {sub.name}", lambda: manager.remove(sub.name))

        if menu.confirm("注册 systemd 服务？", default=True):
            tx.add_undo("卸载 mihomo 服务", lambda: service.remove(purge_runtime=True))
            service.install(start=menu.confirm("现在启动服务？", default=True))

        if menu.confirm("订阅已配置，是否现在切换 / 固定节点？", default=False):
            from .. import node_select
            node_select.select(str(paths.CONFIG_FILE))

        if menu.confirm("安装每周自动更新定时器？", default=False):
            from .. import timer
            tx.add_undo("卸载每周更新定时器", timer.remove)
            timer.install()

        if menu.confirm("安装网络切换自愈？", default=False):
            from .. import resilience
            tx.add_undo("卸载网络自愈", resilience.remove)
            resilience.install()

        shell.ok("初始化完成")
        shell.info("Web UI 默认: http://127.0.0.1:9090/ui")
