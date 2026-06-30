"""防火墙放行：开启局域网代理时放行 mixed 端口。"""

from __future__ import annotations

from . import shell

PROXY_PORT = 7890
_PROTOCOLS = ("tcp", "udp")


def detect() -> str | None:
    if shell._have("ufw"):
        return "ufw"
    if shell._have("firewall-cmd"):
        return "firewalld"
    if shell._have("nft"):
        return "nftables"
    if shell._have("iptables"):
        return "iptables"
    return None


def allow(port: int = PROXY_PORT) -> bool:
    backend = detect()
    if backend is None:
        shell.warn(f"未探测到防火墙工具，请自行确认放行 {port}/tcp,udp。")
        return False
    shell.info(f"经 {backend} 放行 {port}/tcp,udp ...")
    _dispatch(backend, True, port)
    shell.ok(f"已放行 {port} 端口（{backend}）。")
    return True


def revoke(port: int = PROXY_PORT) -> None:
    backend = detect()
    if backend is None:
        return
    shell.info(f"经 {backend} 撤销放行 {port} ...")
    _dispatch(backend, False, port)


def _dispatch(backend: str, add: bool, port: int) -> None:
    if backend == "ufw":
        action = ["allow"] if add else ["delete", "allow"]
        for proto in _PROTOCOLS:
            shell.run_root(["ufw", *action, f"{port}/{proto}"], check=False, reason="更新防火墙")
    elif backend == "firewalld":
        flag = "--add-port" if add else "--remove-port"
        for proto in _PROTOCOLS:
            shell.run_root(["firewall-cmd", "--permanent", f"{flag}={port}/{proto}"], check=False, reason="更新防火墙")
        shell.run_root(["firewall-cmd", "--reload"], check=False, reason="更新防火墙")
    elif backend == "nftables":
        if add:
            for proto in _PROTOCOLS:
                shell.run_root(["nft", "add", "rule", "inet", "filter", "input", proto, "dport", str(port), "accept"], check=False, reason="更新防火墙")
        else:
            shell.warn("nftables 规则请手动移除：nft -a list chain inet filter input 查看句柄后 delete。")
    elif backend == "iptables":
        op = "-I" if add else "-D"
        for proto in _PROTOCOLS:
            shell.run_root(["iptables", op, "INPUT", "-p", proto, "--dport", str(port), "-j", "ACCEPT"], check=False, reason="更新防火墙")

