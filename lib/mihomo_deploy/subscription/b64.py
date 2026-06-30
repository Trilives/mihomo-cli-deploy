"""通用 base64 订阅处理。

mihomo 原生吃 Clash，故 base64 来源只需转成 Clash 配置即可直接部署：

默认路径：把 base64 节点交给云端 subconverter 转成 Clash（target=clash），
云端只负责"解析千奇百怪的节点链接"这件难事；得到的 Clash 配置交 patch 最小改写。

应急路径（base64_local_fallback=true，默认关闭、有风险）：本地直接解析节点分享链接
为 Clash 风格 proxy 字典，再拼成最小可用 Clash 配置。覆盖主流协议，格式怪异时可能漏字段/转错。
"""

from __future__ import annotations

import base64
import json
import urllib.parse

from .. import shell, yamlmini
from . import fetch


def _b64decode(text: str) -> bytes:
    text = text.strip().replace("-", "+").replace("_", "/")
    text += "=" * (-len(text) % 4)
    return base64.b64decode(text)


def to_clash_dict(raw_text: str, cfg: dict) -> dict:
    """base64 内容 → Clash 配置 dict（subconverter 优先，按需本地应急解析）。"""
    backend = str(cfg.get("subconverter_backend") or "")
    proxy = str(cfg.get("download_proxy") or "")
    local_fallback = bool(cfg.get("base64_local_fallback"))

    if backend:
        try:
            clash_yaml = to_clash_via_subconverter(raw_text, backend, proxy=proxy)
            data = yamlmini.load(clash_yaml)
            if isinstance(data, dict) and isinstance(data.get("proxies"), list):
                return data
            raise RuntimeError("subconverter 返回内容无法解析为 Clash。")
        except RuntimeError as exc:
            if not local_fallback:
                raise RuntimeError(
                    f"subconverter 解析失败：{exc}。可更换后端，或开启应急本地解析 base64_local_fallback。"
                ) from exc
            shell.warn(f"subconverter 失败，改用应急本地解析：{exc}")
    elif not local_fallback:
        raise RuntimeError("未配置 subconverter 后端，且未开启应急本地解析（base64_local_fallback）。")

    proxies = local_parse_to_clash(raw_text)
    if not proxies:
        raise RuntimeError("本地解析未得到任何节点。")
    return _minimal_clash(proxies)


def _minimal_clash(proxies: "list[dict]") -> dict:
    """用解析出的 proxies 拼一份最小可用 Clash 配置（一个总 select 组 + 兜底规则）。"""
    names = [p["name"] for p in proxies if p.get("name")]
    return {
        "proxies": proxies,
        "proxy-groups": [
            {"name": "Proxy", "type": "select", "proxies": [*names, "DIRECT"]},
        ],
        "rules": [
            "GEOIP,CN,DIRECT",
            "MATCH,Proxy",
        ],
    }


def to_clash_via_subconverter(raw_text: str, backend: str, *, proxy: str = "") -> str:
    """base64 内容 → subconverter(target=clash) → Clash YAML 文本。"""
    if not backend:
        raise RuntimeError("未配置 subconverter 后端。")
    backend = backend.rstrip("/")
    payload = urllib.parse.quote(raw_text.strip(), safe="")
    url = f"{backend}/sub?target=clash&list=false&url={payload}"
    data = fetch.fetch(url, source_type="clash", proxy=proxy)
    text = data.decode("utf-8", "ignore")
    if "proxies:" not in text:
        raise RuntimeError("subconverter 返回内容不含 proxies，可能后端不可用或订阅无效。")
    return text


# --------------------------------------------------------------------------- #
# 应急本地解析（best-effort）
# --------------------------------------------------------------------------- #
def local_parse_to_clash(raw_text: str) -> "list[dict]":
    """把 base64 订阅解析为 Clash 风格 proxy 字典列表（best-effort）。"""
    try:
        decoded = _b64decode(raw_text).decode("utf-8", "ignore")
    except (ValueError, base64.binascii.Error):  # type: ignore[attr-defined]
        decoded = raw_text
    proxies: list[dict] = []
    for line in decoded.splitlines():
        line = line.strip()
        if not line or "://" not in line:
            continue
        try:
            p = _parse_link(line)
        except Exception:  # noqa: BLE001 - 单条失败不影响其余
            p = None
        if p:
            proxies.append(p)
    return proxies


def _name_from_fragment(url: str) -> str:
    frag = urllib.parse.urlparse(url).fragment
    return urllib.parse.unquote(frag) if frag else ""


def _parse_link(link: str) -> "dict | None":
    scheme = link.split("://", 1)[0].lower()
    if scheme == "vmess":
        return _parse_vmess(link)
    if scheme == "ss":
        return _parse_ss(link)
    if scheme == "trojan":
        return _parse_userinfo(link, "trojan")
    if scheme == "vless":
        return _parse_vless(link)
    if scheme in ("hysteria2", "hy2"):
        return _parse_userinfo(link, "hysteria2")
    if scheme == "tuic":
        return _parse_tuic(link)
    return None


def _parse_vmess(link: str) -> "dict | None":
    raw = link[len("vmess://"):]
    info = json.loads(_b64decode(raw).decode("utf-8", "ignore"))
    name = info.get("ps") or info.get("add") or "vmess"
    p = {
        "name": str(name), "type": "vmess",
        "server": info.get("add"), "port": info.get("port"),
        "uuid": info.get("id"), "alterId": info.get("aid", 0),
        "cipher": info.get("scy") or "auto",
    }
    net = (info.get("net") or "").lower()
    if net in ("ws", "websocket"):
        p["network"] = "ws"
        p["ws-opts"] = {"path": info.get("path") or "/", "headers": {"Host": info.get("host") or info.get("add")}}
    elif net == "grpc":
        p["network"] = "grpc"
        p["grpc-opts"] = {"grpc-service-name": info.get("path") or ""}
    if str(info.get("tls")).lower() in ("tls", "true", "1"):
        p["tls"] = True
        if info.get("sni") or info.get("host"):
            p["servername"] = info.get("sni") or info.get("host")
    return p


def _parse_ss(link: str) -> "dict | None":
    body = link[len("ss://"):]
    name = _name_from_fragment(link)
    body = body.split("#", 1)[0]
    if "@" in body:
        creds, server = body.rsplit("@", 1)
        try:
            creds = _b64decode(creds).decode("utf-8", "ignore")
        except (ValueError, base64.binascii.Error):  # type: ignore[attr-defined]
            pass
    else:
        decoded = _b64decode(body).decode("utf-8", "ignore")
        creds, server = decoded.rsplit("@", 1)
    method, password = creds.split(":", 1)
    host, port = server.rsplit(":", 1)
    return {
        "name": name or host, "type": "ss", "server": host, "port": int(port.split("/")[0].split("?")[0]),
        "cipher": method, "password": password,
    }


def _parse_userinfo(link: str, ptype: str) -> "dict | None":
    u = urllib.parse.urlparse(link)
    q = urllib.parse.parse_qs(u.query)
    p = {
        "name": _name_from_fragment(link) or u.hostname, "type": ptype,
        "server": u.hostname, "port": u.port, "password": urllib.parse.unquote(u.username or ""),
    }
    sni = q.get("sni", q.get("peer", [None]))[0]
    if sni:
        p["servername"] = sni
        p["tls"] = True
    if q.get("insecure", ["0"])[0] in ("1", "true"):
        p["skip-cert-verify"] = True
    return p


def _parse_vless(link: str) -> "dict | None":
    u = urllib.parse.urlparse(link)
    q = urllib.parse.parse_qs(u.query)
    p = {
        "name": _name_from_fragment(link) or u.hostname, "type": "vless",
        "server": u.hostname, "port": u.port, "uuid": u.username,
    }
    if q.get("flow", [None])[0]:
        p["flow"] = q["flow"][0]
    if q.get("security", [""])[0] in ("tls", "reality"):
        p["tls"] = True
        if q.get("sni", [None])[0]:
            p["servername"] = q["sni"][0]
    net = q.get("type", [""])[0]
    if net == "ws":
        p["network"] = "ws"
        p["ws-opts"] = {"path": q.get("path", ["/"])[0], "headers": {"Host": q.get("host", [u.hostname])[0]}}
    elif net == "grpc":
        p["network"] = "grpc"
        p["grpc-opts"] = {"grpc-service-name": q.get("serviceName", [""])[0]}
    return p


def _parse_tuic(link: str) -> "dict | None":
    u = urllib.parse.urlparse(link)
    q = urllib.parse.parse_qs(u.query)
    uuid = urllib.parse.unquote(u.username or "")
    password = urllib.parse.unquote(u.password or "")
    p = {
        "name": _name_from_fragment(link) or u.hostname, "type": "tuic",
        "server": u.hostname, "port": u.port, "uuid": uuid, "password": password,
    }
    if q.get("congestion_control", [None])[0]:
        p["congestion-controller"] = q["congestion_control"][0]
    if q.get("sni", [None])[0]:
        p["servername"] = q["sni"][0]
        p["tls"] = True
    return p
