"""核心资源下载/更新：mihomo 内核 + MetaCubeXD UI + geo 数据。"""

from __future__ import annotations

import gzip
import json
import os
import shutil
import stat
import tarfile
import tempfile
import zipfile
from pathlib import Path

from . import paths, shell

META_RULES_REPO = "MetaCubeX/meta-rules-dat"
MIHOMO_REPO = "MetaCubeX/mihomo"
UI_REPO = "MetaCubeX/metacubexd"
GOOGLE_PROBE_URL = "https://www.google.com/generate_204"

_CURL_COMMON = [
    "-fL",
    "--retry", "3",
    "--connect-timeout", "10",
]

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
}


def _env_file_value(key: str) -> str:
    env_file = paths.ROOT / ".env"
    if not env_file.exists():
        return ""
    for raw in env_file.read_text("utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == key:
            return v.strip().strip("\"'")
    return ""


def _settings() -> dict[str, str]:
    data: dict = {}
    if paths.CUSTOMIZE_FILE.exists():
        try:
            data = json.loads(paths.CUSTOMIZE_FILE.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or _env_file_value("GITHUB_TOKEN")
    proxy = (
        data.get("download_proxy")
        or os.environ.get("DOWNLOAD_PROXY")
        or os.environ.get("ALL_PROXY")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("HTTP_PROXY")
        or _env_file_value("DOWNLOAD_PROXY")
        or ""
    )
    mirror = data.get("github_mirror") or ""
    return {"github_token": token.strip(), "download_proxy": str(proxy).strip(), "github_mirror": str(mirror).strip()}


def _mirror(url: str, mirror: str) -> str:
    if not mirror or "api.github.com" in url:
        return url
    if url.startswith(("https://github.com/", "https://raw.githubusercontent.com/")):
        return mirror.rstrip("/") + "/" + url
    return url


class _Fetcher:
    def __init__(self, proxy: str):
        self.proxy = proxy
        self._direct_ok: bool | None = None

    def _direct_reachable(self) -> bool:
        if self._direct_ok is None:
            rc = shell.run(
                ["curl", "-fsS", "--noproxy", "*", "--connect-timeout", "5", "--max-time", "10", "-o", os.devnull, GOOGLE_PROBE_URL],
                check=False,
                capture=True,
            ).returncode
            self._direct_ok = rc == 0
            if self._direct_ok:
                shell.info("直连可达，跳过代理。")
        return bool(self._direct_ok)

    def _channels(self) -> list[str]:
        if self.proxy and os.environ.get("MIHOMO_NO_PROXY", "0") != "1" and not self._direct_reachable():
            return ["proxy", "direct"]
        return ["direct"]

    def fetch(self, extra: list[str]) -> None:
        last: shell.CommandError | None = None
        channels = self._channels()
        for idx, channel in enumerate(channels):
            channel_args: list[str] = []
            if channel == "proxy":
                channel_args = ["--proxy", self.proxy]
            elif self.proxy:
                channel_args = ["--noproxy", "*"]
            try:
                shell.run(["curl", *_CURL_COMMON, *channel_args, *extra], check=True)
                return
            except shell.CommandError as exc:
                last = exc
                if idx < len(channels) - 1:
                    shell.warn(f"  {channel} 通道失败(curl {exc.returncode})，改直连重试...")
        assert last is not None
        raise last

    def read_json(self, url: str) -> dict:
        settings = _settings()
        with tempfile.NamedTemporaryFile("r+", suffix=".json", delete=True) as tf:
            extra = ["-sS", "-o", tf.name]
            if settings["github_token"]:
                extra += ["-H", f"Authorization: Bearer {settings['github_token']}"]
            extra.append(url)
            self.fetch(extra)
            tf.seek(0)
            return json.loads(tf.read())


def _make_fetcher() -> _Fetcher:
    return _Fetcher(_settings()["download_proxy"])


def _arch() -> str:
    return _ARCH_MAP.get(os.uname().machine, os.uname().machine)


def _latest_release(fetcher: _Fetcher, repo: str) -> dict:
    return fetcher.read_json(f"https://api.github.com/repos/{repo}/releases/latest")


def _asset_urls(release: dict) -> list[str]:
    return [a.get("browser_download_url", "") for a in release.get("assets", []) if a.get("browser_download_url")]


def _pick_asset(urls: list[str], pattern: str) -> str | None:
    import re
    rx = re.compile(pattern, re.IGNORECASE)
    return next((u for u in urls if rx.search(u)), None)


def _download_to(fetcher: _Fetcher, url: str, out: Path, *, force: bool) -> None:
    if not force and out.exists() and out.stat().st_size > 0:
        shell.info(f"使用缓存: {out.name}")
        return
    part = out.with_suffix(out.suffix + ".part")
    part.unlink(missing_ok=True)
    shell.info(f"下载: {url}")
    fetcher.fetch(["-o", str(part), url])
    if part.stat().st_size == 0:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"下载文件为空: {out.name}")
    part.replace(out)


def _extract_archive(archive: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    name = archive.name
    if name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(archive, "r:gz") as t:
            t.extractall(out_dir)
    elif name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(out_dir)
    elif name.endswith(".gz"):
        with gzip.open(archive, "rb") as src, (out_dir / archive.stem).open("wb") as dst:
            shutil.copyfileobj(src, dst)
    else:
        shutil.copy2(archive, out_dir / archive.name)


def update_geo(fetcher: _Fetcher | None = None, *, force: bool = False) -> None:
    paths.ensure_state_dirs()
    f = fetcher or _make_fetcher()
    s = _settings()
    urls = [
        (f"https://github.com/{META_RULES_REPO}/releases/latest/download/country.mmdb", paths.COUNTRY_MMDB),
        (f"https://github.com/{META_RULES_REPO}/releases/latest/download/geoip.metadb", paths.GEOIP_METADB),
    ]
    for url, dest in urls:
        cache = paths.DOWNLOADS_DIR / dest.name
        _download_to(f, _mirror(url, s["github_mirror"]), cache, force=force)
        shutil.copy2(cache, dest)
    shell.ok("geo 数据已更新")


def update_core(fetcher: _Fetcher | None = None, *, variant: str = "standard", force: bool = False) -> str:
    paths.ensure_state_dirs()
    if variant not in {"standard", "compatible"}:
        raise RuntimeError("--variant 只能是 standard 或 compatible")
    f = fetcher or _make_fetcher()
    s = _settings()
    shell.info("查找最新 mihomo 版本...")
    rel = _latest_release(f, MIHOMO_REPO)
    urls = _asset_urls(rel)
    arch = _arch()
    ext = r"(\.gz|\.tgz|\.tar\.gz|\.zip)"
    url = None
    if variant == "compatible":
        url = _pick_asset(urls, rf"mihomo-linux-{arch}-compatible-v[0-9][^/]*{ext}$")
    url = url or _pick_asset(urls, rf"mihomo-linux-{arch}-v[0-9][^/]*{ext}$")
    url = url or _pick_asset(urls, rf"mihomo-linux-{arch}-compatible-v[0-9][^/]*{ext}$")
    url = url or _pick_asset(urls, rf"mihomo-linux-{arch}[^/]*{ext}$")
    if not url:
        raise RuntimeError(f"未找到架构 {arch} 的 Linux mihomo 资源")
    version = rel.get("tag_name", "").strip()
    archive = paths.DOWNLOADS_DIR / Path(url).name
    _download_to(f, _mirror(url, s["github_mirror"]), archive, force=force)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _extract_archive(archive, tmp)
        binpath = next((p for p in tmp.rglob("*") if p.is_file() and (p.name.startswith("mihomo") or p.name.startswith("clash"))), None)
        binpath = binpath or next((p for p in tmp.rglob("*") if p.is_file()), None)
        if binpath is None:
            raise RuntimeError("解压后未找到 mihomo 可执行文件")
        shutil.copy2(binpath, paths.MIHOMO_BIN)
        paths.MIHOMO_BIN.chmod(paths.MIHOMO_BIN.stat().st_mode | stat.S_IEXEC | 0o755)
    if version:
        paths.MIHOMO_VERSION_FILE.write_text(version + "\n", "utf-8")
    shell.ok(f"内核已部署: {version or 'unknown'}")
    return version


def update_ui(fetcher: _Fetcher | None = None, *, force: bool = False) -> None:
    paths.ensure_state_dirs()
    f = fetcher or _make_fetcher()
    s = _settings()
    shell.info("查找最新 MetaCubeXD UI...")
    rel = _latest_release(f, UI_REPO)
    urls = _asset_urls(rel)
    url = _pick_asset(urls, r"(gh-pages|dist).*(\.zip|\.tar\.gz|\.tgz)$") or _pick_asset(urls, r"(\.zip|\.tar\.gz|\.tgz)$")
    if not url:
        raise RuntimeError("未找到 MetaCubeXD UI 发布资源")
    archive = paths.DOWNLOADS_DIR / Path(url).name
    _download_to(f, _mirror(url, s["github_mirror"]), archive, force=force)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _extract_archive(archive, tmp)
        indexes = list(tmp.rglob("index.html"))
        ui_root = next((p.parent for p in indexes if (p.parent / "assets").exists() or (p.parent / "_nuxt").exists()), None)
        ui_root = ui_root or (indexes[0].parent if indexes else None)
        if ui_root is None:
            raise RuntimeError("解压后未找到 UI index.html")
        shutil.rmtree(paths.UI_DIR, ignore_errors=True)
        shutil.copytree(ui_root, paths.UI_DIR)
    shell.ok("Web UI 已更新")


def sync_legacy_copies() -> None:
    """写出根目录兼容副本，便于沿用旧命令排查。"""
    if paths.MIHOMO_BIN.exists():
        shutil.copy2(paths.MIHOMO_BIN, paths.LEGACY_MIHOMO_BIN)
    if paths.MIHOMO_VERSION_FILE.exists():
        shutil.copy2(paths.MIHOMO_VERSION_FILE, paths.LEGACY_VERSION_FILE)
    if paths.COUNTRY_MMDB.exists():
        shutil.copy2(paths.COUNTRY_MMDB, paths.LEGACY_COUNTRY_MMDB)
    if paths.GEOIP_METADB.exists():
        shutil.copy2(paths.GEOIP_METADB, paths.LEGACY_GEOIP_METADB)
    if paths.UI_DIR.exists():
        shutil.rmtree(paths.LEGACY_UI_DIR, ignore_errors=True)
        shutil.copytree(paths.UI_DIR, paths.LEGACY_UI_DIR)


def download_all(*, variant: str = "standard", force: bool = False) -> None:
    f = _make_fetcher()
    update_geo(f, force=force)
    update_core(f, variant=variant, force=force)
    update_ui(f, force=force)
    sync_legacy_copies()


def run(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="mihomo_deploy.core")
    p.add_argument("--only", choices=["all", "core", "ui", "geo"], default="all")
    p.add_argument("--variant", choices=["standard", "compatible"], default=os.environ.get("MIHOMO_VARIANT", "standard"))
    p.add_argument("--force", action="store_true")
    args = p.parse_args(argv)
    try:
        if args.only == "all":
            download_all(variant=args.variant, force=args.force)
        elif args.only == "core":
            update_core(variant=args.variant, force=args.force)
            sync_legacy_copies()
        elif args.only == "ui":
            update_ui(force=args.force)
            sync_legacy_copies()
        else:
            update_geo(force=args.force)
            sync_legacy_copies()
    except (RuntimeError, shell.CommandError) as exc:
        shell.error(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())

