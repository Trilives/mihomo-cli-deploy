from __future__ import annotations

from .. import menu


def normalize_proxy(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    if "://" in raw:
        return raw
    return "http://" + raw


def strip_scheme(value: str) -> str:
    for prefix in ("http://", "https://", "socks5h://", "socks5://"):
        if value.startswith(prefix):
            return value[len(prefix):]
    return value


def ask_new_subscription() -> tuple[str, str, str, bool] | None:
    name = menu.ask("订阅名称", default="default", allow_empty=False)
    idx = menu.select("订阅类型", ["Clash/Mihomo YAML（推荐）", "通用订阅，经 subconverter 转 Clash"], back_label="取消")
    source_type = "clash" if idx == 0 else "base64"
    url = menu.ask("订阅链接（留空取消）", allow_empty=True)
    if not url:
        return None
    customize_flag = menu.confirm("生成定制分组（SG/HK url-test/fallback）？默认保留机场原分组", default=False)
    return name, url, source_type, customize_flag
