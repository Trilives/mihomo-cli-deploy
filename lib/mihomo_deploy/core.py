"""核心资源下载/更新：mihomo 内核 + Web UI + geo 数据。

移植自 sing-box 版 core.py，按 mihomo 调整：
- 内核仓库 MetaCubeX/mihomo；资产为 `mihomo-linux-<arch>-<tag>.gz`（gzip 单文件，
  非 tar.gz），用标准库 gzip 解压。
- geo 数据（geoip.metadb + geosite.dat）**默认下载**：机场订阅的 rules 普遍内联
  GEOIP/GEOSITE，缺 geo 数据 mihomo 会校验失败（见 ARCHITECTURE.md §9）。
- Web UI 仍用 MetaCubeX/metacubexd（Clash API 面板通用）。
- 下载仍用 curl 子进程：保留"代理优先→直连兜底"通道、重试、断点续传、完整性校验。

下载相关设置（download_proxy / github_mirror / github_token）从 state/customize.json 读取，
未配置时回退环境变量（github_token 回退 GITHUB_TOKEN / GH_TOKEN）/ 直连。
本模块不依赖 customize.py，直接读 JSON，避免循环依赖。
"""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import stat
import tarfile
import tempfile
import zipfile
from pathlib import Path

from . import paths, shell

MIHOMO_REPO = "MetaCubeX/mihomo"
UI_REPO = "MetaCubeX/metacubexd"
# geo 数据：MetaCubeX/meta-rules-dat 的 latest 滚动发布
GEO_BASE = "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest"
GEOIP_URL = f"{GEO_BASE}/geoip.metadb"
GEOSITE_URL = f"{GEO_BASE}/geosite.dat"

GOOGLE_PROBE_URL = "https://www.google.com/generate_204"

_CURL_COMMON = [
    "-fL",
    "--retry", "5",
    "--retry-delay", "2",
    "--retry-all-errors",
    "--connect-timeout", "10",
    "--speed-time", "30",
    "--speed-limit", "1024",
]

# uname.machine → go arch（mihomo 资产命名用 go arch）
_ARCH_MAP = {
    "x86_64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
    "armv7l": "armv7",
    "armv7": "armv7",
    "armv6l": "armv6",
    "armv6": "armv6",
    "i386": "386",
    "i686": "386",
    "riscv64": "riscv64",
    "s390x": "s390x",
    "loongarch64": "loong64",
    "mips64": "mips64",
}


# --------------------------------------------------------------------------- #
# 设置读取
# --------------------------------------------------------------------------- #
def _settings() -> dict:
    """读 state/customize.json 中与下载相关的字段（容错，缺失返回默认）。"""
    data: dict = {}
    if paths.CUSTOMIZE_FILE.exists():
        try:
            data = json.loads(paths.CUSTOMIZE_FILE.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    proxy = data.get("download_proxy") or os.environ.get("DOWNLOAD_PROXY") or ""
    mirror = data.get("github_mirror") or ""
    token = data.get("github_token") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    return {"download_proxy": proxy.strip(), "github_mirror": mirror.strip(), "github_token": token.strip()}


def _prompt_and_save_token() -> str:
    """未配置 GitHub Token 时交互式询问是否补充，输入后写回 customize.json。

    非 TTY（如每周定时更新）静默跳过，避免无人值守时卡在读输入。
    """
    from . import keys, menu

    if not keys.interactive_tty():
        return ""
    shell.warn("未配置 GitHub Token，匿名 API 限额较低（60 次/小时），高频操作易被限流。")
    try:
        if not menu.confirm("现在添加 GitHub Token？", default=False):
            return ""
        token = menu.ask("GitHub Token", allow_empty=True)
    except menu.Cancelled:
        return ""
    if not token:
        return ""
    data: dict = {}
    if paths.CUSTOMIZE_FILE.exists():
        try:
            data = json.loads(paths.CUSTOMIZE_FILE.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    if not isinstance(data, dict):
        data = {}
    data["github_token"] = token
    paths.ensure_state_dirs()
    paths.CUSTOMIZE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")
    shell.ok("GitHub Token 已保存到 customize.json。")
    return token


def _mirror(url: str, mirror: str) -> str:
    """对 GitHub 下载/raw 链接套加速前缀；api.github.com 不套（多数镜像不代理 API）。"""
    if not mirror:
        return url
    if "api.github.com" in url:
        return url
    if url.startswith(("https://github.com/", "https://raw.githubusercontent.com/")):
        return mirror.rstrip("/") + "/" + url
    return url


# --------------------------------------------------------------------------- #
# curl 通道：代理优先 → 直连兜底
# --------------------------------------------------------------------------- #
class _Fetcher:
    def __init__(self, proxy: str, token: str = ""):
        self.proxy = proxy
        self.token = token
        self._direct_ok: bool | None = None

    def _direct_reachable(self) -> bool:
        if self._direct_ok is None:
            rc = shell.run(
                ["curl", "-fsS", "--noproxy", "*", "--connect-timeout", "5",
                 "--max-time", "10", "-o", os.devnull, GOOGLE_PROBE_URL],
                check=False, capture=True,
            ).returncode
            self._direct_ok = rc == 0
            if self._direct_ok:
                shell.info("直连可达，跳过代理。")
        return bool(self._direct_ok)

    def _channels(self) -> list[str]:
        no_proxy = os.environ.get("MIHOMO_NO_PROXY", "0") == "1"
        if self.proxy and not no_proxy and not self._direct_reachable():
            return ["proxy", "direct"]
        return ["direct"]

    def fetch(self, extra: list[str]) -> None:
        """按通道顺序尝试 curl，首个成功即返回；全失败抛 CommandError。"""
        channels = self._channels()
        last_exc: shell.CommandError | None = None
        for i, ch in enumerate(channels):
            chan_args: list[str] = []
            if ch == "proxy":
                chan_args = ["--proxy", self.proxy]
            elif ch == "direct" and self.proxy:
                chan_args = ["--noproxy", "*"]
            try:
                shell.run(["curl", *_CURL_COMMON, *chan_args, *extra], check=True)
                return
            except shell.CommandError as exc:
                last_exc = exc
                if i < len(channels) - 1:
                    shell.warn(f"  {ch} 通道失败(curl {exc.returncode})，改直连重试…")
        assert last_exc is not None
        raise last_exc

    def read_json(self, url: str) -> dict:
        """拉取 URL 文本并解析 JSON（用于 GitHub API）。"""
        with tempfile.NamedTemporaryFile("r+", suffix=".json", delete=True) as tf:
            extra = ["-sS", "-o", tf.name]
            if self.token:
                extra += ["-H", f"Authorization: Bearer {self.token}"]
            extra.append(url)
            self.fetch(extra)
            tf.seek(0)
            return json.loads(tf.read())


# --------------------------------------------------------------------------- #
# GitHub Release 解析
# --------------------------------------------------------------------------- #
def _arch() -> str:
    machine = os.uname().machine
    return _ARCH_MAP.get(machine, machine)


def _latest_release(fetcher: _Fetcher, repo: str) -> dict:
    return fetcher.read_json(f"https://api.github.com/repos/{repo}/releases/latest")


def _asset_urls(release: dict) -> list[str]:
    return [a.get("browser_download_url", "") for a in release.get("assets", [])]


def _pick_asset(urls: list[str], pattern: str) -> str | None:
    rx = re.compile(pattern, re.IGNORECASE)
    for u in urls:
        if rx.search(u):
            return u
    return None


def _pick_mihomo_asset(urls: list[str], arch: str, version: str, *, compatible: bool) -> str | None:
    """选 mihomo Linux 内核 .gz 资产。

    资产形如 mihomo-linux-amd64-v1.19.27.gz（标准）/ -compatible-（老 CPU）/
    -v1|v2|v3-（amd64 微架构）/ -go120|go123-（旧 glibc）。默认选标准包（最大兼容），
    compatible=True 时优先老 CPU 兜底包。只认 .gz，排除 deb/rpm/pkg。
    """
    v = re.escape(version)
    std = rf"mihomo-linux-{arch}-{v}\.gz$"
    compat = rf"mihomo-linux-{arch}-compatible-{v}\.gz$"
    order = [compat, std] if compatible else [std, compat]
    # 兜底：任意 arch 变体的 .gz（含微架构 / go 版本后缀）
    order.append(rf"mihomo-linux-{arch}[^/]*-{v}\.gz$")
    order.append(rf"mihomo-linux-{arch}[^/]*\.gz$")
    for pat in order:
        u = _pick_asset(urls, pat)
        if u:
            return u
    return None


# --------------------------------------------------------------------------- #
# 下载 + 缓存校验
# --------------------------------------------------------------------------- #
def _cache_valid(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    name = path.name
    try:
        if name.endswith((".tar.gz", ".tgz")):
            with tarfile.open(path, "r:gz") as t:
                t.getmembers()
        elif name.endswith(".zip"):
            with zipfile.ZipFile(path) as z:
                if z.testzip() is not None:
                    return False
        elif name.endswith(".gz"):
            with gzip.open(path, "rb") as g:
                while g.read(1 << 20):
                    pass
    except (tarfile.TarError, zipfile.BadZipFile, OSError, EOFError):
        return False
    return True


def _download_to(fetcher: _Fetcher, url: str, out: Path, *, force: bool) -> None:
    part = out.with_suffix(out.suffix + ".part")
    if not force and _cache_valid(out):
        shell.info(f"使用缓存: {out.name}")
        return
    if out.exists():
        shell.info(f"丢弃无效缓存: {out.name}")
        out.unlink(missing_ok=True)
        part.unlink(missing_ok=True)
    resume = ["-C", "-"] if part.exists() and part.stat().st_size > 0 else []
    shell.info(f"下载: {url}")
    fetcher.fetch([*resume, "-o", str(part), url])
    # 校验（压缩包/gz）；其它只查非空
    if part.name.endswith((".tar.gz", ".tgz", ".zip", ".gz")) and not _cache_valid(part):
        part.unlink(missing_ok=True)
        raise RuntimeError(f"下载文件完整性校验失败: {out.name}")
    if part.stat().st_size == 0:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"下载文件为空: {out.name}")
    part.replace(out)


# --------------------------------------------------------------------------- #
# 部署各组件
# --------------------------------------------------------------------------- #
def update_core(fetcher: _Fetcher | None = None, *, compatible: bool = False, force: bool = False) -> str:
    """下载并部署 mihomo 内核（gzip 单文件），返回版本号。"""
    paths.ensure_state_dirs()
    f = fetcher or _make_fetcher()
    s = _settings()
    shell.info("查找最新 mihomo 版本…")
    rel = _latest_release(f, MIHOMO_REPO)
    version = rel.get("tag_name", "").strip()
    urls = _asset_urls(rel)
    arch = _arch()
    url = _pick_mihomo_asset(urls, arch, version, compatible=compatible)
    if not url:
        raise RuntimeError(f"未找到架构 {arch} 的 Linux mihomo 资源")

    archive = paths.DOWNLOADS_DIR / Path(url).name
    _download_to(f, _mirror(url, s["github_mirror"]), archive, force=force)

    # gzip 单文件解压 → mihomo 可执行
    paths.BIN_DIR.mkdir(parents=True, exist_ok=True)
    tmp = paths.MIHOMO_BIN.with_suffix(".new")
    with gzip.open(archive, "rb") as src, open(tmp, "wb") as dst:
        shutil.copyfileobj(src, dst)
    tmp.chmod(tmp.stat().st_mode | stat.S_IEXEC | 0o755)
    tmp.replace(paths.MIHOMO_BIN)
    paths.MIHOMO_VERSION_FILE.write_text(version + "\n", "utf-8")
    shell.ok(f"内核已部署: {version}")
    return version


def update_geodata(fetcher: _Fetcher | None = None, *, force: bool = False) -> None:
    """下载 mihomo geo 数据（geoip.metadb + geosite.dat）。

    机场订阅 rules 普遍内联 GEOIP/GEOSITE，缺 geo 数据会导致 mihomo 校验/运行失败，
    故默认下载。
    """
    paths.ensure_state_dirs()
    f = fetcher or _make_fetcher()
    s = _settings()
    for url, dest in ((GEOIP_URL, paths.GEOIP_METADB), (GEOSITE_URL, paths.GEOSITE_DAT)):
        cache = paths.DOWNLOADS_DIR / dest.name
        _download_to(f, _mirror(url, s["github_mirror"]), cache, force=force)
        shutil.copy2(cache, dest)
    shell.ok("geo 数据已更新")


def update_ui(fetcher: _Fetcher | None = None, *, force: bool = False) -> None:
    """下载并部署 Web UI（metacubexd）。"""
    paths.ensure_state_dirs()
    f = fetcher or _make_fetcher()
    s = _settings()
    shell.info("查找最新 Web UI 版本…")
    rel = _latest_release(f, UI_REPO)
    urls = _asset_urls(rel)
    url = _pick_asset(urls, r"(gh-pages|dist|compressed-dist).*(\.zip|\.tar\.gz|\.tgz)$") \
        or _pick_asset(urls, r"(\.zip|\.tar\.gz|\.tgz)$")
    if not url:
        raise RuntimeError(f"未从 {UI_REPO} releases 找到 UI 资源")
    archive = paths.DOWNLOADS_DIR / Path(url).name
    _download_to(f, _mirror(url, s["github_mirror"]), archive, force=force)

    with tempfile.TemporaryDirectory() as td:
        _extract(archive, Path(td))
        ui_root = _find_ui_root(Path(td))
        if ui_root is None:
            raise RuntimeError(f"未能定位 UI 根目录: {archive.name}")
        if paths.UI_DIR.exists():
            shutil.rmtree(paths.UI_DIR)
        shutil.copytree(ui_root, paths.UI_DIR)
    shell.ok("Web UI 已部署")


def _extract(archive: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if archive.name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(archive, "r:gz") as t:
            t.extractall(out_dir)
    elif archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(out_dir)
    else:
        raise RuntimeError(f"不支持的压缩格式: {archive.name}")


def _find_ui_root(extract_dir: Path) -> Path | None:
    indexes = list(extract_dir.rglob("index.html"))
    for idx in indexes:
        d = idx.parent
        if (d / "assets").is_dir() or (d / "_nuxt").is_dir():
            return d
    return indexes[0].parent if indexes else None


def _make_fetcher(*, interactive: bool = True) -> _Fetcher:
    s = _settings()
    if s["download_proxy"]:
        shell.info(f"使用下载代理: {s['download_proxy']}")
    token = s["github_token"]
    if not token and interactive:
        token = _prompt_and_save_token()
    return _Fetcher(s["download_proxy"], token)


def download_all(*, compatible: bool = False, force: bool = False, interactive: bool = True) -> str:
    """下载内核 + geo 数据 + UI，返回内核版本。

    interactive=False 供无人值守场景（如每周定时更新）使用，跳过 Token 缺失时的交互询问。
    """
    f = _make_fetcher(interactive=interactive)
    version = update_core(f, compatible=compatible, force=force)
    update_geodata(f, force=force)
    update_ui(f, force=force)
    return version


# --------------------------------------------------------------------------- #
# 独立调用入口
# --------------------------------------------------------------------------- #
def run(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="mihomo_deploy.core", description="下载/更新 内核+UI+geo数据")
    p.add_argument("--compatible", action="store_true", help="选用兼容老 CPU 的内核变体")
    p.add_argument("--force", action="store_true", help="忽略下载缓存")
    p.add_argument("--only", choices=["core", "ui", "geo"], help="只更新某一项")
    args = p.parse_args(argv)
    try:
        if args.only == "core":
            update_core(compatible=args.compatible, force=args.force)
        elif args.only == "ui":
            update_ui(force=args.force)
        elif args.only == "geo":
            update_geodata(force=args.force)
        else:
            download_all(compatible=args.compatible, force=args.force)
    except (RuntimeError, shell.CommandError) as exc:
        shell.error(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
