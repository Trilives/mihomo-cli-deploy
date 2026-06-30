"""把代理环境变量写入用户 ~/.bashrc（未启用 TUN 时的便利项）。"""

from __future__ import annotations

import os
from pathlib import Path

from . import shell

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 7890

_BEGIN = "# >>> mihomo proxy env >>>"
_END = "# <<< mihomo proxy env <<<"


def _block() -> str:
    http = f"http://{PROXY_HOST}:{PROXY_PORT}"
    socks = f"socks5://{PROXY_HOST}:{PROXY_PORT}"
    return "\n".join([
        _BEGIN,
        f'export http_proxy="{http}"',
        f'export https_proxy="{http}"',
        f'export all_proxy="{socks}"',
        'export HTTP_PROXY="$http_proxy"',
        'export HTTPS_PROXY="$https_proxy"',
        'export ALL_PROXY="$all_proxy"',
        'export no_proxy="localhost,127.0.0.1,::1"',
        'export NO_PROXY="$no_proxy"',
        _END,
    ])


def target_bashrc() -> Path:
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user and sudo_user != "root":
        try:
            import pwd
            home = pwd.getpwnam(sudo_user).pw_dir
        except KeyError:
            home = os.path.expanduser("~")
    else:
        home = os.path.expanduser("~")
    return Path(home) / ".bashrc"


def _strip_block(text: str) -> str:
    lines = text.splitlines()
    out, skip = [], False
    for line in lines:
        if line.strip() == _BEGIN:
            skip = True
            continue
        if line.strip() == _END:
            skip = False
            continue
        if not skip:
            out.append(line)
    return "\n".join(out)


def write() -> Path:
    path = target_bashrc()
    existed = path.exists()
    old = path.read_text("utf-8") if existed else ""
    body = _strip_block(old).rstrip("\n")
    new = (body + "\n\n" if body else "") + _block() + "\n"
    path.write_text(new, "utf-8")
    if not existed:
        _chown_to_sudo_user(path)
    shell.ok(f"已写入代理环境变量到 {path}（新开终端生效）。")
    return path


def remove() -> None:
    path = target_bashrc()
    if not path.exists():
        return
    old = path.read_text("utf-8")
    if _BEGIN not in old:
        return
    path.write_text(_strip_block(old).rstrip("\n") + "\n", "utf-8")
    shell.ok(f"已从 {path} 移除代理环境变量。")


def _chown_to_sudo_user(path: Path) -> None:
    sudo_user = os.environ.get("SUDO_USER")
    if not sudo_user or sudo_user == "root" or os.geteuid() != 0:
        return
    try:
        import pwd
        pw = pwd.getpwnam(sudo_user)
        os.chown(path, pw.pw_uid, pw.pw_gid)
    except (KeyError, OSError):
        pass

