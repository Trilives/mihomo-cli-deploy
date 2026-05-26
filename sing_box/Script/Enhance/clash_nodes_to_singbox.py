#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import socket
import shutil
import sys
import tempfile
from collections import Counter
from ipaddress import ip_address
from pathlib import Path
from typing import Any, NamedTuple

import yaml


RESERVED_TAGS = {"Proxy", "AI", "Auto", "SG-Auto", "Fallback", "DIRECT", "BLOCK", "DNS"}
DEFAULT_PREFER = "Singapore,SG,新加坡,狮城"
DEFAULT_OUTBOUND_CHOICES = ("Proxy", "Auto", "AI", "SG-Auto")
SING_BOX_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CUSTOM_CONFIG_PATH = Path(__file__).with_name("clash_nodes_to_singbox_config.json")

AI_DOMAIN_SUFFIXES = [
    "openai.com",
    "chatgpt.com",
    "oaistatic.com",
    "oaiusercontent.com",
    "anthropic.com",
    "claude.ai",
    "github.com",
    "githubusercontent.com",
    "githubassets.com",
    "github.io",
    "huggingface.co",
    "hf.co",
    "npmjs.com",
    "npmjs.org",
    "pypi.org",
    "pythonhosted.org",
    "files.pythonhosted.org",
    "docker.com",
    "docker.io",
    "ghcr.io",
]

CN_DOMAIN_SUFFIXES = ["cn", "com.cn", "net.cn", "org.cn", "gov.cn", "edu.cn"]
LOCAL_BYPASS_DOMAINS = ["localhost"]
LOCAL_BYPASS_IP_CIDRS = ["127.0.0.0/8", "0.0.0.0/8", "::1/128"]
# Do not exclude 172.16.0.0/12: it contains the TUN-derived DNS address 172.19.0.2.
# Other private destinations still match the later ip_is_private DIRECT route rule.
PRIVATE_BYPASS_IP_CIDRS = [
    "10.0.0.0/8",
    "192.168.0.0/16",
    "169.254.0.0/16",
    "fc00::/7",
    "fe80::/10",
]
OVERLAY_BYPASS_IP_CIDRS = [
    "100.64.0.0/10",
    "fd7a:115c:a1e0::/48",
    "10.126.126.0/24",
    "10.14.14.0/24",
]
ROUTE_EXCLUDE_IP_CIDRS = LOCAL_BYPASS_IP_CIDRS + PRIVATE_BYPASS_IP_CIDRS + OVERLAY_BYPASS_IP_CIDRS
BYPASS_PROCESS_NAMES = [
    "easytier",
    "easytier-cli",
    "easytier-core",
    "tailscale",
    "tailscaled",
]


class CustomConfig(NamedTuple):
    ai_domain_suffixes: list[str]
    cn_domain_suffixes: list[str]
    local_bypass_domains: list[str]
    route_exclude_ip_cidrs: list[str]
    bypass_process_names: list[str]
    easytier_bypass_domains: list[str]
    easytier_bypass_ip_cidrs: list[str]


DEFAULT_CUSTOM_CONFIG = CustomConfig(
    ai_domain_suffixes=AI_DOMAIN_SUFFIXES,
    cn_domain_suffixes=CN_DOMAIN_SUFFIXES,
    local_bypass_domains=LOCAL_BYPASS_DOMAINS,
    route_exclude_ip_cidrs=ROUTE_EXCLUDE_IP_CIDRS,
    bypass_process_names=BYPASS_PROCESS_NAMES,
    easytier_bypass_domains=[],
    easytier_bypass_ip_cidrs=[],
)


class ConversionError(Exception):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ConversionError(f"Invalid YAML in input file: {path}") from exc
    except OSError as exc:
        raise ConversionError(f"Failed to read input file: {path}") from exc

    if not isinstance(data, dict):
        raise ConversionError("Input YAML root must be a mapping.")
    return data


def normalize_string_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConversionError(f"custom config {field} must be a list")
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def load_custom_config(path: Path) -> CustomConfig:
    if not path.exists():
        return DEFAULT_CUSTOM_CONFIG
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise ConversionError(f"Invalid JSON in custom config file: {path}") from exc
    except OSError as exc:
        raise ConversionError(f"Failed to read custom config file: {path}") from exc

    if not isinstance(data, dict):
        raise ConversionError("custom config root must be a mapping")

    return CustomConfig(
        ai_domain_suffixes=normalize_string_list(data.get("ai_domain_suffixes"), "ai_domain_suffixes")
        or AI_DOMAIN_SUFFIXES,
        cn_domain_suffixes=normalize_string_list(data.get("cn_domain_suffixes"), "cn_domain_suffixes")
        or CN_DOMAIN_SUFFIXES,
        local_bypass_domains=normalize_string_list(data.get("local_bypass_domains"), "local_bypass_domains")
        or LOCAL_BYPASS_DOMAINS,
        route_exclude_ip_cidrs=normalize_string_list(data.get("route_exclude_ip_cidrs"), "route_exclude_ip_cidrs")
        or ROUTE_EXCLUDE_IP_CIDRS,
        bypass_process_names=normalize_string_list(data.get("bypass_process_names"), "bypass_process_names")
        or BYPASS_PROCESS_NAMES,
        easytier_bypass_domains=normalize_string_list(data.get("easytier_bypass_domains"), "easytier_bypass_domains"),
        easytier_bypass_ip_cidrs=normalize_string_list(
            data.get("easytier_bypass_ip_cidrs"), "easytier_bypass_ip_cidrs"
        ),
    )


def resolve_domains_to_cidrs(domains: list[str]) -> list[str]:
    cidrs: list[str] = []
    for domain in domains:
        try:
            records = socket.getaddrinfo(domain, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            print(f"warning: failed to resolve easytier bypass domain {domain}: {exc}")
            continue

        for record in records:
            address = record[4][0]
            try:
                parsed = ip_address(address)
            except ValueError:
                continue
            cidr = f"{parsed}/{parsed.max_prefixlen}"
            if cidr not in cidrs:
                cidrs.append(cidr)
    return cidrs


def validate_output_path(path: Path) -> Path:
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(SING_BOX_DIR)
    except ValueError as exc:
        raise ConversionError(f"Output file must be inside the sing_box directory: {SING_BOX_DIR}") from exc
    return resolved_path


def write_json_config(config: dict[str, Any], output_path: Path) -> None:
    try:
        payload = json.dumps(config, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    except (TypeError, ValueError) as exc:
        raise ConversionError("Failed to serialize generated JSON.") from exc

    temporary_path: Path | None = None
    replacing_existing = output_path.exists()
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=output_path.parent, prefix=f".{output_path.name}.", delete=False
        ) as temporary_file:
            temporary_file.write(payload)
            temporary_path = Path(temporary_file.name)
        temporary_path.replace(output_path)
    except OSError as exc:
        raise ConversionError(f"Failed to write output JSON: {output_path}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    if replacing_existing:
        print(f"Replaced existing output JSON: {output_path}")


def normalize_port(value: Any) -> int | None:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return None
    if 1 <= port <= 65535:
        return port
    return None


def make_safe_tag(name: str, used_tags: set[str]) -> str:
    base = str(name).strip() or "node"
    tag = base
    index = 1
    while tag in used_tags or tag in RESERVED_TAGS:
        tag = f"{base}-{index}"
        index += 1
    used_tags.add(tag)
    return tag


def parse_prefer_keywords(value: str) -> list[str]:
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def is_preferred_node(name: str, prefer_keywords: list[str]) -> bool:
    lowered = name.lower()
    return any(keyword in lowered for keyword in prefer_keywords)


def require_fields(proxy: dict[str, Any], fields: list[str]) -> str | None:
    for field in fields:
        if proxy.get(field) in (None, ""):
            return f"missing {field}"
    if normalize_port(proxy.get("port", proxy.get("server_port"))) is None:
        return "missing or invalid port"
    return None


def base_outbound(proxy: dict[str, Any], tag: str, outbound_type: str) -> dict[str, Any]:
    server = proxy.get("server")
    port = normalize_port(proxy.get("server_port", proxy.get("port")))
    if not server:
        raise ConversionError("missing server")
    if port is None:
        raise ConversionError("missing or invalid port")
    return {
        "type": outbound_type,
        "tag": tag,
        "server": str(server),
        "server_port": port,
    }


def tls_config(proxy: dict[str, Any], default_enabled: bool = False) -> dict[str, Any] | None:
    enabled = bool(proxy.get("tls", default_enabled))
    server_name = proxy.get("servername") or proxy.get("server_name") or proxy.get("sni")
    insecure = proxy.get("skip-cert-verify")
    alpn = proxy.get("alpn")
    fingerprint = proxy.get("client-fingerprint") or proxy.get("fingerprint")

    if not enabled and not server_name and insecure is None and not alpn and not fingerprint:
        return None

    tls: dict[str, Any] = {"enabled": enabled or bool(server_name or alpn or fingerprint)}
    if server_name:
        tls["server_name"] = str(server_name)
    if insecure is not None:
        tls["insecure"] = bool(insecure)
    if isinstance(alpn, list):
        tls["alpn"] = [str(item) for item in alpn]
    elif isinstance(alpn, str) and alpn:
        tls["alpn"] = [item.strip() for item in alpn.split(",") if item.strip()]
    if fingerprint:
        # sing-box 1.13 still supports TLS uTLS. Keep only the conservative fingerprint mapping.
        tls["utls"] = {"enabled": True, "fingerprint": str(fingerprint)}
    return tls


def websocket_transport(proxy: dict[str, Any]) -> dict[str, Any] | None:
    network = str(proxy.get("network", "")).lower()
    if network not in {"ws", "websocket"}:
        return None
    opts = proxy.get("ws-opts") if isinstance(proxy.get("ws-opts"), dict) else {}
    transport: dict[str, Any] = {"type": "ws"}
    if opts.get("path"):
        transport["path"] = str(opts["path"])
    headers = opts.get("headers")
    if isinstance(headers, dict) and headers:
        transport["headers"] = {str(k): str(v) for k, v in headers.items()}
    return transport


def grpc_transport(proxy: dict[str, Any]) -> dict[str, Any] | None:
    network = str(proxy.get("network", "")).lower()
    if network != "grpc":
        return None
    opts = proxy.get("grpc-opts") if isinstance(proxy.get("grpc-opts"), dict) else {}
    transport: dict[str, Any] = {"type": "grpc"}
    service_name = opts.get("grpc-service-name") or opts.get("serviceName") or opts.get("service_name")
    if service_name:
        transport["service_name"] = str(service_name)
    return transport


def httpupgrade_transport(proxy: dict[str, Any]) -> dict[str, Any] | None:
    network = str(proxy.get("network", "")).lower()
    if network not in {"httpupgrade", "http-upgrade"}:
        return None
    opts = proxy.get("httpupgrade-opts") if isinstance(proxy.get("httpupgrade-opts"), dict) else {}
    transport: dict[str, Any] = {"type": "httpupgrade"}
    if opts.get("path"):
        transport["path"] = str(opts["path"])
    host = opts.get("host")
    if isinstance(host, list):
        transport["host"] = [str(item) for item in host]
    elif host:
        transport["host"] = [str(host)]
    return transport


def add_supported_transport(proxy: dict[str, Any], outbound: dict[str, Any]) -> str | None:
    network = str(proxy.get("network", "")).lower()
    if not network or network in {"tcp", "raw"}:
        return None
    transport = websocket_transport(proxy) or grpc_transport(proxy) or httpupgrade_transport(proxy)
    if transport:
        outbound["transport"] = transport
        return None
    return f"unsupported transport {network}"


def convert_proxy(proxy: dict[str, Any], used_tags: set[str]) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(proxy, dict):
        return None, "proxy is not a mapping"
    name = str(proxy.get("name") or "").strip()
    if not name:
        return None, "missing name"

    tag = make_safe_tag(name, used_tags)
    proxy_type = str(proxy.get("type") or "").lower().strip()
    converters = {
        "anytls": convert_anytls,
        "trojan": convert_trojan,
        "ss": convert_shadowsocks,
        "shadowsocks": convert_shadowsocks,
        "vmess": convert_vmess,
        "vless": convert_vless,
        "hysteria2": convert_hysteria2,
        "hy2": convert_hysteria2,
        "tuic": convert_tuic,
        "socks": convert_socks,
        "socks5": convert_socks,
        "http": convert_http,
    }
    converter = converters.get(proxy_type)
    if converter is None:
        used_tags.discard(tag)
        return None, f"unsupported type {proxy_type or 'unknown'}"

    try:
        outbound = converter(proxy, tag)
    except ConversionError as exc:
        used_tags.discard(tag)
        return None, str(exc)
    return outbound, None


def convert_anytls(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    reason = require_fields(proxy, ["server", "password"])
    if reason:
        raise ConversionError(reason)
    outbound = base_outbound(proxy, tag, "anytls")
    outbound["password"] = str(proxy["password"])
    outbound["tls"] = tls_config(proxy, default_enabled=True) or {"enabled": True}
    return outbound


def convert_trojan(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    reason = require_fields(proxy, ["server", "password"])
    if reason:
        raise ConversionError(reason)
    outbound = base_outbound(proxy, tag, "trojan")
    outbound["password"] = str(proxy["password"])
    tls = tls_config(proxy, default_enabled=True)
    if tls:
        outbound["tls"] = tls
    transport_error = add_supported_transport(proxy, outbound)
    if transport_error:
        raise ConversionError(transport_error)
    return outbound


def convert_shadowsocks(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    reason = require_fields(proxy, ["server", "cipher", "password"])
    if reason:
        raise ConversionError(reason)
    outbound = base_outbound(proxy, tag, "shadowsocks")
    outbound["method"] = str(proxy["cipher"])
    outbound["password"] = str(proxy["password"])
    plugin = str(proxy.get("plugin") or "").lower()
    if plugin:
        if plugin != "obfs":
            raise ConversionError(f"unsupported shadowsocks plugin {plugin}")
        opts = proxy.get("plugin-opts") if isinstance(proxy.get("plugin-opts"), dict) else {}
        mode = str(opts.get("mode") or "http").lower()
        host = opts.get("host")
        if mode not in {"http", "tls"}:
            raise ConversionError(f"unsupported shadowsocks obfs mode {mode}")
        plugin_opts = f"obfs={mode}"
        if host:
            plugin_opts += f";obfs-host={host}"
        outbound["plugin"] = "obfs-local"
        outbound["plugin_opts"] = plugin_opts
    return outbound


def convert_vmess(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    reason = require_fields(proxy, ["server", "uuid"])
    if reason:
        raise ConversionError(reason)
    outbound = base_outbound(proxy, tag, "vmess")
    outbound["uuid"] = str(proxy["uuid"])
    outbound["security"] = str(proxy.get("cipher") or "auto")
    outbound["alter_id"] = int(proxy.get("alterId") or proxy.get("alter-id") or 0)
    tls = tls_config(proxy)
    if tls:
        outbound["tls"] = tls
    transport_error = add_supported_transport(proxy, outbound)
    if transport_error:
        raise ConversionError(transport_error)
    return outbound


def convert_vless(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    reason = require_fields(proxy, ["server", "uuid"])
    if reason:
        raise ConversionError(reason)
    outbound = base_outbound(proxy, tag, "vless")
    outbound["uuid"] = str(proxy["uuid"])
    flow = proxy.get("flow")
    if flow:
        outbound["flow"] = str(flow)
    tls = tls_config(proxy)
    if tls:
        outbound["tls"] = tls
    transport_error = add_supported_transport(proxy, outbound)
    if transport_error:
        raise ConversionError(transport_error)
    return outbound


def convert_hysteria2(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    reason = require_fields(proxy, ["server", "password"])
    if reason:
        raise ConversionError(reason)
    outbound = base_outbound(proxy, tag, "hysteria2")
    outbound["password"] = str(proxy["password"])
    tls = tls_config(proxy, default_enabled=True)
    if tls:
        outbound["tls"] = tls
    return outbound


def convert_tuic(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    reason = require_fields(proxy, ["server", "uuid", "password"])
    if reason:
        raise ConversionError(reason)
    outbound = base_outbound(proxy, tag, "tuic")
    outbound["uuid"] = str(proxy["uuid"])
    outbound["password"] = str(proxy["password"])
    congestion_control = proxy.get("congestion-controller") or proxy.get("congestion_control")
    if congestion_control:
        outbound["congestion_control"] = str(congestion_control)
    tls = tls_config(proxy, default_enabled=True)
    if tls:
        outbound["tls"] = tls
    return outbound


def convert_socks(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    reason = require_fields(proxy, ["server"])
    if reason:
        raise ConversionError(reason)
    outbound = base_outbound(proxy, tag, "socks")
    if proxy.get("username"):
        outbound["username"] = str(proxy["username"])
    if proxy.get("password"):
        outbound["password"] = str(proxy["password"])
    return outbound


def convert_http(proxy: dict[str, Any], tag: str) -> dict[str, Any]:
    reason = require_fields(proxy, ["server"])
    if reason:
        raise ConversionError(reason)
    outbound = base_outbound(proxy, tag, "http")
    if proxy.get("username"):
        outbound["username"] = str(proxy["username"])
    if proxy.get("password"):
        outbound["password"] = str(proxy["password"])
    tls = tls_config(proxy)
    if tls:
        outbound["tls"] = tls
    return outbound


def build_easytier_ip_cidrs(
    custom_config: CustomConfig,
    easytier_resolved_ip_cidrs: list[str] | None = None,
) -> list[str]:
    cidrs = list(custom_config.easytier_bypass_ip_cidrs)
    for cidr in easytier_resolved_ip_cidrs or []:
        if cidr not in cidrs:
            cidrs.append(cidr)
    return cidrs


def build_inbounds(
    custom_config: CustomConfig = DEFAULT_CUSTOM_CONFIG,
    easytier_resolved_ip_cidrs: list[str] | None = None,
) -> list[dict[str, Any]]:
    route_exclude_address = list(custom_config.route_exclude_ip_cidrs)
    for cidr in build_easytier_ip_cidrs(custom_config, easytier_resolved_ip_cidrs):
        if cidr not in route_exclude_address:
            route_exclude_address.append(cidr)
    return [
        {
            "type": "tun",
            "tag": "tun-in",
            "interface_name": "singbox",
            "address": ["172.19.0.1/30"],
            "mtu": 1400,
            "auto_route": True,
            "strict_route": True,
            "route_exclude_address": route_exclude_address,
            "stack": "gvisor",
        },
        {
            "type": "mixed",
            "tag": "mixed-in",
            "listen": "127.0.0.1",
            "listen_port": 7890,
        },
    ]


def build_dns(custom_config: CustomConfig = DEFAULT_CUSTOM_CONFIG) -> dict[str, Any]:
    rules = [
        {"domain": custom_config.local_bypass_domains, "server": "local"},
        {"domain_suffix": custom_config.cn_domain_suffixes, "server": "local"},
        {"domain_suffix": custom_config.ai_domain_suffixes, "server": "remote"},
    ]
    if custom_config.easytier_bypass_domains:
        rules.insert(1, {"domain": custom_config.easytier_bypass_domains, "server": "local"})
    return {
        "servers": [
            {"type": "udp", "tag": "local", "server": "223.5.5.5", "server_port": 53},
            {
                "type": "https",
                "tag": "remote",
                "server": "1.1.1.1",
                "server_port": 443,
                "path": "/dns-query",
                "tls": {"server_name": "cloudflare-dns.com"},
                "detour": "AI",
            },
        ],
        "rules": rules,
        # Keep local/CN lookups direct; route all other domain lookups through proxied DoH.
        # Proxy-node bootstrap uses route.default_domain_resolver instead of this fallback.
        "final": "remote",
        "strategy": "prefer_ipv4",
    }


def build_experimental(output_path: Path) -> dict[str, Any]:
    return {
        "clash_api": {
            "external_controller": "0.0.0.0:9090",
            "external_ui": "ui",
            "default_mode": "rule",
            "access_control_allow_private_network": True,
        }
    }


def build_route(
    default_outbound: str,
    has_sg_auto: bool,
    custom_config: CustomConfig = DEFAULT_CUSTOM_CONFIG,
    easytier_resolved_ip_cidrs: list[str] | None = None,
) -> dict[str, Any]:
    if default_outbound == "SG-Auto" and not has_sg_auto:
        default_outbound = "Proxy"
    easytier_ip_cidrs = build_easytier_ip_cidrs(custom_config, easytier_resolved_ip_cidrs)
    rules: list[dict[str, Any]] = [
        {"process_name": custom_config.bypass_process_names, "action": "route", "outbound": "DIRECT"},
        {"domain": custom_config.local_bypass_domains, "action": "route", "outbound": "DIRECT"},
    ]
    if custom_config.easytier_bypass_domains:
        rules.append({"domain": custom_config.easytier_bypass_domains, "action": "route", "outbound": "DIRECT"})
    if easytier_ip_cidrs:
        rules.append({"ip_cidr": easytier_ip_cidrs, "action": "route", "outbound": "DIRECT"})
    rules.extend(
        [
            {"ip_cidr": custom_config.route_exclude_ip_cidrs, "action": "route", "outbound": "DIRECT"},
            {"action": "sniff"},
            {"protocol": "dns", "action": "hijack-dns"},
            {"ip_is_private": True, "action": "route", "outbound": "DIRECT"},
            {"domain_suffix": custom_config.ai_domain_suffixes, "action": "route", "outbound": "AI"},
            {"domain_suffix": custom_config.cn_domain_suffixes, "action": "route", "outbound": "DIRECT"},
            # TODO: For complete CN split routing, add sing-box rule_set files later.
            # The old geoip/geosite fields are intentionally not emitted for 1.13+ compatibility.
        ]
    )
    return {
        "auto_detect_interface": True,
        "default_domain_resolver": "local",
        "rules": rules,
        "final": default_outbound,
    }


def build_outbounds(
    converted_nodes: list[dict[str, Any]], prefer_keywords: list[str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    node_tags = [node["tag"] for node in converted_nodes]
    sg_tags = [tag for tag in node_tags if is_preferred_node(tag, prefer_keywords)]
    has_sg_auto = bool(sg_tags)

    outbounds: list[dict[str, Any]] = list(converted_nodes)
    if has_sg_auto:
        outbounds.append(
            {
                "type": "urltest",
                "tag": "SG-Auto",
                "outbounds": sg_tags,
                "url": "https://www.gstatic.com/generate_204",
                "interval": "5m",
                "tolerance": 50,
            }
        )

    outbounds.append(
        {
            "type": "urltest",
            "tag": "Auto",
            "outbounds": node_tags,
            "url": "https://www.gstatic.com/generate_204",
            "interval": "5m",
            "tolerance": 50,
        }
    )

    ai_default = "SG-Auto" if has_sg_auto else "Auto"
    ai_outbounds = ["SG-Auto", "Auto", "DIRECT"] if has_sg_auto else ["Auto", "DIRECT"]
    outbounds.append({"type": "selector", "tag": "AI", "outbounds": ai_outbounds, "default": ai_default})

    proxy_default = "SG-Auto" if has_sg_auto else "Auto"
    proxy_outbounds = ["AI"]
    if has_sg_auto:
        proxy_outbounds.append("SG-Auto")
    proxy_outbounds.extend(["Auto", *node_tags, "DIRECT"])
    outbounds.append(
        {"type": "selector", "tag": "Proxy", "outbounds": proxy_outbounds, "default": proxy_default}
    )

    outbounds.extend(
        [
            {
                "type": "selector",
                "tag": "Fallback",
                "outbounds": ["Proxy", "Auto", "DIRECT"],
                "default": "Proxy",
            },
            {"type": "direct", "tag": "DIRECT"},
            {"type": "block", "tag": "BLOCK"},
        ]
    )
    return outbounds, {
        "has_sg_auto": has_sg_auto,
        "sg_count": len(sg_tags),
        "auto_count": len(node_tags),
        "proxy_default": proxy_default,
        "ai_default": ai_default,
    }


def build_singbox_config(
    converted_nodes: list[dict[str, Any]],
    prefer_keywords: list[str],
    default_outbound: str,
    output_path: Path,
    custom_config: CustomConfig = DEFAULT_CUSTOM_CONFIG,
    easytier_resolved_ip_cidrs: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    outbounds, outbound_info = build_outbounds(converted_nodes, prefer_keywords)
    if default_outbound == "SG-Auto" and not outbound_info["has_sg_auto"]:
        print("warning: --default-outbound SG-Auto requested but SG-Auto was not generated; using Proxy")
        default_outbound = "Proxy"
    config = {
        "log": {"level": "warning"},
        "dns": build_dns(custom_config),
        "inbounds": build_inbounds(custom_config, easytier_resolved_ip_cidrs),
        "outbounds": outbounds,
        "route": build_route(
            default_outbound,
            outbound_info["has_sg_auto"],
            custom_config,
            easytier_resolved_ip_cidrs,
        ),
        "experimental": build_experimental(output_path),
    }
    return config, outbound_info


def validate_config_basic(config: dict[str, Any]) -> None:
    if not isinstance(config, dict):
        raise ConversionError("config must be a dict")
    for key in ("inbounds", "outbounds"):
        if not isinstance(config.get(key), list) or not config[key]:
            raise ConversionError(f"{key} must be a non-empty list")
    if not isinstance(config.get("route"), dict):
        raise ConversionError("route must exist")
    if not isinstance(config.get("dns"), dict):
        raise ConversionError("dns must exist")
    clash_api = (config.get("experimental") or {}).get("clash_api")
    if not isinstance(clash_api, dict):
        raise ConversionError("experimental.clash_api must exist")
    if not clash_api.get("external_controller") or not clash_api.get("external_ui"):
        raise ConversionError("clash_api external_controller and external_ui must exist")

    tags: list[str] = []
    for outbound in config["outbounds"]:
        if not isinstance(outbound, dict) or not outbound.get("type") or not outbound.get("tag"):
            raise ConversionError("each outbound must have type and tag")
        tags.append(outbound["tag"])
    tag_set = set(tags)
    if len(tags) != len(tag_set):
        raise ConversionError("outbound tags must be unique")

    for outbound in config["outbounds"]:
        if outbound["type"] in {"selector", "urltest"}:
            refs = outbound.get("outbounds")
            if not isinstance(refs, list) or not refs:
                raise ConversionError(f"{outbound['tag']} outbounds must be non-empty")
            missing = [ref for ref in refs if ref not in tag_set]
            if missing:
                raise ConversionError(f"{outbound['tag']} references missing outbounds: {missing}")
    route_final = config["route"].get("final")
    if route_final not in tag_set:
        raise ConversionError(f"route final references missing outbound: {route_final}")
    if "SG-Auto" in tag_set:
        sg_auto = next(item for item in config["outbounds"] if item["tag"] == "SG-Auto")
        if not sg_auto.get("outbounds"):
            raise ConversionError("SG-Auto outbounds must be non-empty")
    auto = next((item for item in config["outbounds"] if item["tag"] == "Auto"), None)
    if not auto or not auto.get("outbounds"):
        raise ConversionError("Auto outbounds must be non-empty")


def print_summary(
    input_path: Path,
    output_path: Path,
    total: int,
    converted_nodes: list[dict[str, Any]],
    skipped_reasons: Counter[str],
    outbound_info: dict[str, Any],
) -> None:
    print()
    print("Summary:")
    print(f"  Input file: {input_path}")
    print(f"  Output file: {output_path}")
    print(f"  proxies total: {total}")
    print(f"  converted: {len(converted_nodes)}")
    print(f"  skipped: {sum(skipped_reasons.values())}")
    if skipped_reasons:
        print("  skipped reasons:")
        for reason, count in skipped_reasons.most_common():
            print(f"    {reason}: {count}")
    print("  node tags: omitted from logs")
    print(f"  contains anytls: {any(node['type'] == 'anytls' for node in converted_nodes)}")
    print(f"  SG-Auto generated: {outbound_info['has_sg_auto']}")
    print(f"  SG-Auto node count: {outbound_info['sg_count']}")
    print(f"  Auto node count: {outbound_info['auto_count']}")
    print(f"  Proxy default outbound: {outbound_info['proxy_default']}")
    print(f"  AI default outbound: {outbound_info['ai_default']}")
    print("  Clash API controller: 0.0.0.0:9090")
    print("  Web UI path: ui (relative to the configuration directory)")
    print("  Web UI URL: http://<LAN-IP>:9090/ui")
    obfs_count = sum(1 for node in converted_nodes if node.get("plugin") == "obfs-local")
    print(f"  obfs-local required: {obfs_count > 0}")
    if obfs_count:
        print(f"  obfs-local node count: {obfs_count}")
        if shutil.which("obfs-local"):
            print("  obfs-local command: found")
        else:
            print("  obfs-local command: not found")
            print("  warning: ss obfs nodes need obfs-local installed, or connections will fail at runtime")
    print()
    print("Check command:")
    print("  ./sing_box/sing-box check -c ./sing_box/config.json")
    if not Path("sing_box/sing-box").exists():
        print("  Local ./sing_box/sing-box not found; you can also run:")
        print("  sing-box check -c ./sing_box/config.json")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract Clash/Mihomo proxies and generate a conservative sing-box TUN config."
    )
    parser.add_argument("input", nargs="?", default="./config.yaml", help="Clash/Mihomo config.yaml")
    parser.add_argument("output", nargs="?", default="./sing_box/config.json", help="sing-box config.json")
    parser.add_argument("--prefer", default=DEFAULT_PREFER, help="comma separated preferred node keywords")
    parser.add_argument("--default-outbound", default="Proxy", choices=DEFAULT_OUTBOUND_CHOICES)
    parser.add_argument(
        "--custom-config",
        default=str(DEFAULT_CUSTOM_CONFIG_PATH),
        help="JSON file for custom DNS, route, process, and easytier bypass settings",
    )
    parser.add_argument("--strict", action="store_true", help="exit on unsupported or incomplete nodes")
    parser.add_argument(
        "--skip-unsupported",
        action="store_true",
        help="skip unsupported nodes; kept for explicit CLI compatibility",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    prefer_keywords = parse_prefer_keywords(args.prefer)

    try:
        output_path = validate_output_path(Path(args.output))
        custom_config_path = Path(args.custom_config)
        custom_config = load_custom_config(custom_config_path)
        easytier_resolved_ip_cidrs = resolve_domains_to_cidrs(custom_config.easytier_bypass_domains)
        data = load_yaml(input_path)
        proxies = data.get("proxies")
        if proxies is None:
            raise ConversionError("proxies field does not exist in input YAML.")
        if not isinstance(proxies, list):
            raise ConversionError("proxies field must be a list.")
        if not proxies:
            raise ConversionError("proxies field is empty.")

        used_tags = set(RESERVED_TAGS)
        converted_nodes: list[dict[str, Any]] = []
        skipped_reasons: Counter[str] = Counter()
        for proxy in proxies:
            outbound, reason = convert_proxy(proxy, used_tags)
            if reason:
                print(f"warning: skipped proxy node: {reason}")
                skipped_reasons[reason] += 1
                if args.strict:
                    raise ConversionError(f"strict mode: skipped proxy node: {reason}")
                continue
            assert outbound is not None
            converted_nodes.append(outbound)

        if not converted_nodes:
            raise ConversionError("No proxy nodes were converted successfully.")

        if not any(is_preferred_node(node["tag"], prefer_keywords) for node in converted_nodes):
            print("warning: no preferred Singapore nodes matched; SG-Auto will not be generated")

        config, outbound_info = build_singbox_config(
            converted_nodes,
            prefer_keywords,
            args.default_outbound,
            output_path,
            custom_config,
            easytier_resolved_ip_cidrs,
        )
        validate_config_basic(config)
        write_json_config(config, output_path)

        print_summary(input_path, output_path, len(proxies), converted_nodes, skipped_reasons, outbound_info)
        return 0
    except ConversionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
