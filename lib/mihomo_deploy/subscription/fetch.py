"""订阅拉取与 subconverter 转换。"""

from __future__ import annotations

from urllib.parse import urlencode

from .. import shell


def _curl(url: str, *, proxy: str = "") -> bytes:
    cmd = ["curl", "-fL", "--retry", "3", "--connect-timeout", "10", "-sS"]
    if proxy:
        cmd += ["--proxy", proxy]
    result = shell.run([*cmd, url], capture=True)
    return (result.stdout or "").encode("utf-8")


def direct(url: str, *, proxy: str = "") -> bytes:
    return _curl(url, proxy=proxy)


def converted(
    url: str,
    *,
    backend: str,
    proxy: str = "",
    target: str = "clash",
    extra_params: list[str] | None = None,
) -> bytes:
    params: list[tuple[str, str]] = [("target", target), ("url", url)]
    for item in extra_params or []:
        if "=" not in item:
            raise RuntimeError(f"subconverter 参数必须是 k=v: {item}")
        key, value = item.split("=", 1)
        params.append((key, value))
    convert_url = backend.rstrip("/") + "/sub?" + urlencode(params)
    return _curl(convert_url, proxy=proxy)

