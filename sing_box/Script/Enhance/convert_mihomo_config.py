#!/usr/bin/env python3
"""Convert a Mihomo/Clash YAML config to a sing-box JSON config.

The converter targets the structures used by this repository's config.yaml and
writes all sing-box output under sing_box/ by default.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


JsonDict = dict[str, Any]

DIRECT_TAG = "direct"
BLOCK_TAG = "block"
DEFAULT_TEST_URL = "https://www.gstatic.com/generate_204"
DIRECT_PROCESS_NAMES = [
    "tailscaled",
    "tailscale",
    "easytier-core",
    "easytier-cli",
    "sshd",
    "ssh",
]
PRIVATE_ROUTE_CIDRS = [
    "0.0.0.0/8",
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "224.0.0.0/4",
    "240.0.0.0/4",
    "::1/128",
    "fc00::/7",
    "fe80::/10",
]
DEFAULT_LOG_LEVEL = "warning"
RULE_SET_URLS = {
    "geoip": "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/{tag}.srs",
    "geosite": "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/{tag}.srs",
}


def dns_strategy(config: JsonDict) -> str | None:
    dns = config.get("dns") or {}
    if isinstance(dns, dict) and dns.get("ipv6") is False:
        return "ipv4_only"
    if config.get("ipv6") is False:
        return "ipv4_only"
    return None


def convert_log_level(config: JsonDict) -> str:
    level = config.get("log-level")
    if not isinstance(level, str) or level.lower() == "info":
        return DEFAULT_LOG_LEVEL
    return level


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    sing_box_dir = script_dir.parent.parent
    repo_dir = sing_box_dir.parent

    parser = argparse.ArgumentParser(
        description="Convert Mihomo/Clash config.yaml to sing-box config.json."
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=repo_dir / "config.yaml",
        help="source Mihomo config path (default: ./config.yaml)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=sing_box_dir / "config.json",
        help="output sing-box config path (default: ./sing_box/config.json)",
    )
    parser.add_argument(
        "--no-tun",
        action="store_true",
        help="do not emit a sing-box tun inbound even if Mihomo tun is enabled",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> JsonDict:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except FileNotFoundError as exc:
        raise SystemExit(f"Error: input config not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise SystemExit(f"Error: failed to parse YAML {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise SystemExit(f"Error: YAML root must be a mapping: {path}")
    return data


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def compact_dict(data: JsonDict) -> JsonDict:
    return {key: value for key, value in data.items() if value not in (None, [], {})}


def split_host_port(value: str, default_port: int) -> tuple[str, int]:
    parsed = urlparse(value if "://" in value else f"//{value}")
    host = parsed.hostname or value
    port = parsed.port or default_port
    return host, port


def is_ip_literal(value: str) -> bool:
    return all(part.isdigit() for part in value.split(".")) or ":" in value


def normalize_outbound_tag(tag: str) -> str:
    upper_tag = tag.upper()
    if upper_tag == "DIRECT":
        return DIRECT_TAG
    if upper_tag in {"REJECT", "REJECT-DROP"}:
        return BLOCK_TAG
    return tag


def backslash_escape(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("=", r"\=").replace(";", r"\;")


def first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def normalize_headers(value: Any) -> dict[str, list[str]] | None:
    if not isinstance(value, dict):
        return None

    headers: dict[str, list[str]] = {}
    for key, raw_value in value.items():
        if not isinstance(key, str):
            continue
        if isinstance(raw_value, list):
            header_values = [str(item) for item in raw_value]
        else:
            header_values = [str(raw_value)]
        headers[key] = header_values
    return headers or None


def convert_tls(proxy: JsonDict, enabled_by_default: bool = False) -> JsonDict | None:
    reality_opts = proxy.get("reality-opts") or {}
    has_reality = isinstance(reality_opts, dict) and bool(reality_opts.get("public-key"))
    if not (proxy.get("tls") or enabled_by_default or has_reality):
        return None

    tls: JsonDict = {
        "enabled": True,
        "disable_sni": proxy.get("disable-sni"),
        "server_name": first_string(
            proxy.get("servername"), proxy.get("sni"), proxy.get("server")
        ),
        "insecure": proxy.get("skip-cert-verify"),
        "alpn": proxy.get("alpn"),
    }

    fingerprint = first_string(proxy.get("client-fingerprint"), proxy.get("fingerprint"))
    if fingerprint:
        tls["utls"] = {"enabled": True, "fingerprint": fingerprint}

    if has_reality:
        tls["reality"] = compact_dict(
            {
                "enabled": True,
                "public_key": reality_opts.get("public-key"),
                "short_id": reality_opts.get("short-id"),
            }
        )

    return compact_dict(tls)


def convert_transport(proxy: JsonDict) -> JsonDict | None:
    network = proxy.get("network")
    ws_opts = proxy.get("ws-opts") or {}
    grpc_opts = proxy.get("grpc-opts") or {}
    h2_opts = proxy.get("h2-opts") or {}
    http_opts = proxy.get("http-opts") or {}

    if not isinstance(ws_opts, dict):
        ws_opts = {}
    if not isinstance(grpc_opts, dict):
        grpc_opts = {}
    if not isinstance(h2_opts, dict):
        h2_opts = {}
    if not isinstance(http_opts, dict):
        http_opts = {}

    if network == "ws" or ws_opts.get("path"):
        transport_type = "httpupgrade" if ws_opts.get("v2ray-http-upgrade") else "ws"
        headers = normalize_headers(proxy.get("ws-headers")) or normalize_headers(
            ws_opts.get("headers")
        )
        transport = {
            "type": transport_type,
            "path": ws_opts.get("path"),
            "headers": headers,
            "early_data_header_name": ws_opts.get("early-data-header-name"),
            "max_early_data": ws_opts.get("max-early-data"),
        }
        if transport_type == "httpupgrade":
            transport["host"] = first_string(
                proxy.get("servername"), (ws_opts.get("headers") or {}).get("Host")
            )
        return compact_dict(transport)

    if network == "grpc" or grpc_opts.get("grpc-service-name"):
        return compact_dict(
            {"type": "grpc", "service_name": grpc_opts.get("grpc-service-name")}
        )

    if network == "h2" or h2_opts.get("path"):
        return compact_dict(
            {"type": "http", "host": h2_opts.get("host"), "path": h2_opts.get("path")}
        )

    if network == "http" or http_opts.get("path") or http_opts.get("headers"):
        path = http_opts.get("path")
        if isinstance(path, list):
            path = path[0] if path else None
        headers = normalize_headers(http_opts.get("headers"))
        return compact_dict(
            {
                "type": "http",
                "host": (headers or {}).get("Host"),
                "path": path,
                "method": http_opts.get("method"),
                "headers": headers,
            }
        )

    return None


def convert_multiplex(proxy: JsonDict) -> JsonDict | None:
    smux = proxy.get("smux") or {}
    if not isinstance(smux, dict) or not smux.get("enabled"):
        return None
    return compact_dict(
        {
            "enabled": True,
            "max_connections": smux.get("max-connections"),
            "min_streams": smux.get("min-streams"),
            "max_streams": smux.get("max-streams"),
            "padding": smux.get("padding"),
            "protocol": smux.get("protocol"),
        }
    )


def common_proxy_fields(proxy: JsonDict, outbound_type: str, name: str) -> JsonDict:
    return compact_dict(
        {
            "type": outbound_type,
            "tag": name,
            "server": proxy.get("server"),
            "server_port": proxy.get("port"),
            "password": proxy.get("password"),
            "tcp_fast_open": proxy.get("tfo"),
            "tcp_multi_path": proxy.get("mptcp"),
            "multiplex": convert_multiplex(proxy),
        }
    )


def convert_ss_plugin(proxy: JsonDict) -> tuple[str | None, str | None]:
    plugin = proxy.get("plugin")
    plugin_opts = proxy.get("plugin-opts") or {}
    if not plugin:
        return None, None

    if plugin == "obfs":
        mode = plugin_opts.get("mode", "http")
        host = plugin_opts.get("host")
        options = [f"obfs={backslash_escape(mode)}"]
        if host:
            options.append(f"obfs-host={backslash_escape(host)}")
        return "obfs-local", ";".join(options)

    if plugin == "v2ray-plugin":
        opts = []
        for key, value in plugin_opts.items():
            if isinstance(value, bool):
                if value:
                    opts.append(str(key))
            else:
                opts.append(f"{key}={backslash_escape(value)}")
        return "v2ray-plugin", ";".join(opts)

    return None, None


def convert_shadowsocks(proxy: JsonDict, name: str) -> tuple[list[JsonDict] | None, str | None]:
    plugin_opts = proxy.get("plugin-opts") or {}
    if proxy.get("plugin") == "shadow-tls":
        if not isinstance(plugin_opts, dict):
            return None, f"invalid shadow-tls plugin options: {name}"
        detour_tag = f"{name}-shadowtls"
        ss_outbound = common_proxy_fields(proxy, "shadowsocks", name)
        ss_outbound.pop("server", None)
        ss_outbound.pop("server_port", None)
        ss_outbound.update(
            compact_dict(
                {
                    "method": proxy.get("cipher"),
                    "detour": detour_tag,
                }
            )
        )
        shadow_tls = compact_dict(
            {
                "type": "shadowtls",
                "tag": detour_tag,
                "server": proxy.get("server"),
                "server_port": proxy.get("port"),
                "version": plugin_opts.get("version"),
                "password": plugin_opts.get("password"),
                "tls": compact_dict(
                    {"enabled": True, "server_name": plugin_opts.get("host")}
                ),
            }
        )
        return [ss_outbound, shadow_tls], None

    plugin, plugin_opts_value = convert_ss_plugin(proxy)
    outbound = common_proxy_fields(proxy, "shadowsocks", name)
    outbound.update(
        compact_dict(
            {
                "method": proxy.get("cipher"),
                "plugin": plugin,
                "plugin_opts": plugin_opts_value,
                "udp_over_tcp": compact_dict(
                    {
                        "enabled": True,
                        "version": proxy.get("udp-over-tcp-version") or 1,
                    }
                )
                if proxy.get("udp-over-tcp")
                else None,
            }
        )
    )
    return [outbound], None


def convert_vmess_like(proxy: JsonDict, name: str, outbound_type: str) -> JsonDict:
    outbound = common_proxy_fields(proxy, outbound_type, name)
    outbound.update(
        compact_dict(
            {
                "uuid": proxy.get("uuid"),
                "alter_id": proxy.get("alterId"),
                "security": proxy.get("cipher") if outbound_type == "vmess" else None,
                "flow": proxy.get("flow") if outbound_type == "vless" else None,
                "packet_encoding": proxy.get("packet-encoding") or proxy.get("packet_encoding"),
                "global_padding": proxy.get("global-padding"),
                "authenticated_length": proxy.get("authenticated-length"),
                "tls": convert_tls(proxy),
                "transport": convert_transport(proxy),
            }
        )
    )
    return outbound


def convert_proxy(proxy: JsonDict) -> tuple[list[JsonDict] | None, str | None]:
    proxy_type = proxy.get("type")
    name = proxy.get("name")
    if not isinstance(name, str):
        return None, "proxy without a string name"

    if proxy_type == "ss":
        return convert_shadowsocks(proxy, name)
    if proxy_type in {"vmess", "vless"}:
        return [convert_vmess_like(proxy, name, proxy_type)], None
    if proxy_type == "trojan":
        outbound = common_proxy_fields(proxy, "trojan", name)
        outbound.update(
            compact_dict(
                {"tls": convert_tls(proxy, enabled_by_default=True), "transport": convert_transport(proxy)}
            )
        )
        return [outbound], None
    if proxy_type in {"socks5", "http"}:
        outbound_type = "socks" if proxy_type == "socks5" else "http"
        outbound = common_proxy_fields(proxy, outbound_type, name)
        outbound.update(
            compact_dict(
                {
                    "username": proxy.get("username"),
                    "tls": convert_tls(proxy),
                }
            )
        )
        return [outbound], None

    return None, f"unsupported proxy type {proxy_type!r}: {name}"


def filter_existing_tags(tags: list[Any], known_tags: set[str]) -> list[str]:
    result = []
    for tag in tags:
        if not isinstance(tag, str):
            continue
        normalized = normalize_outbound_tag(tag)
        if normalized in known_tags and normalized not in result:
            result.append(normalized)
    return result


def convert_group(group: JsonDict, known_tags: set[str]) -> tuple[JsonDict | None, str | None]:
    name = group.get("name")
    group_type = group.get("type")
    if not isinstance(name, str):
        return None, "proxy group without a string name"

    outbounds = filter_existing_tags(ensure_list(group.get("proxies")), known_tags)
    if not outbounds:
        return None, f"proxy group has no usable outbounds: {name}"

    if group_type == "select":
        return (
            compact_dict(
                {
                    "type": "selector",
                    "tag": name,
                    "outbounds": outbounds,
                    "default": outbounds[0],
                }
            ),
            None,
        )

    if group_type in {"url-test", "fallback", "load-balance"}:
        return (
            compact_dict(
                {
                    "type": "urltest",
                    "tag": name,
                    "outbounds": outbounds,
                    "url": group.get("url") or DEFAULT_TEST_URL,
                    "interval": seconds_to_duration(group.get("interval")),
                    "tolerance": group.get("tolerance"),
                }
            ),
            None,
        )

    return None, f"unsupported proxy group type {group_type!r}: {name}"


def seconds_to_duration(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, int):
        return f"{value}s"
    if isinstance(value, str):
        return value
    return None


def convert_inbounds(config: JsonDict, no_tun: bool) -> list[JsonDict]:
    inbounds: list[JsonDict] = []
    allow_lan = bool(config.get("allow-lan"))
    listen = "0.0.0.0" if allow_lan else "127.0.0.1"

    mixed_port = config.get("mixed-port")
    if isinstance(mixed_port, int):
        inbounds.append(
            {"type": "mixed", "tag": "mixed-in", "listen": listen, "listen_port": mixed_port}
        )

    socks_port = config.get("socks-port")
    if isinstance(socks_port, int):
        inbounds.append(
            {"type": "socks", "tag": "socks-in", "listen": listen, "listen_port": socks_port}
        )

    http_port = config.get("port")
    if isinstance(http_port, int):
        inbounds.append(
            {"type": "http", "tag": "http-in", "listen": listen, "listen_port": http_port}
        )

    tun = config.get("tun") or {}
    if not no_tun and isinstance(tun, dict) and tun.get("enable"):
        stack = tun.get("stack")
        inbound = compact_dict(
            {
                "type": "tun",
                "tag": "tun-in",
                "address": ["172.19.0.1/30"],
                "route_exclude_address": PRIVATE_ROUTE_CIDRS,
                "stack": stack.lower() if isinstance(stack, str) else stack,
                "auto_route": tun.get("auto-route"),
                "strict_route": True,
            }
        )
        inbounds.append(inbound)

    return inbounds


def convert_dns_server(raw_server: Any, index: int) -> JsonDict | None:
    if not isinstance(raw_server, str):
        return None

    if raw_server.startswith("tls://"):
        host, port = split_host_port(raw_server.removeprefix("tls://"), 853)
        server = {"type": "tls", "tag": f"dns-{index}", "server": host, "server_port": port}
        if index != 1 and not is_ip_literal(host):
            server["domain_resolver"] = "dns-1"
        return server

    if raw_server.startswith("https://"):
        parsed = urlparse(raw_server)
        server = compact_dict(
            {
                "type": "https",
                "tag": f"dns-{index}",
                "server": parsed.hostname,
                "server_port": parsed.port or 443,
                "path": parsed.path or "/dns-query",
            }
        )
        if index != 1 and parsed.hostname and not is_ip_literal(parsed.hostname):
            server["domain_resolver"] = "dns-1"
        return server

    server = raw_server.removeprefix("udp://")
    host, port = split_host_port(server, 53)
    return {"type": "udp", "tag": f"dns-{index}", "server": host, "server_port": port}


def domain_filter_to_rule(value: str, server_tag: str) -> JsonDict | None:
    if value.startswith("+."):
        return {"domain_suffix": [value[2:]], "action": "route", "server": server_tag}
    if value.startswith("*."):
        return {"domain_suffix": [value[2:]], "action": "route", "server": server_tag}
    if "*" in value:
        regex = "^" + value.replace(".", r"\.").replace("*", ".*") + "$"
        return {"domain_regex": [regex], "action": "route", "server": server_tag}
    return {"domain": [value], "action": "route", "server": server_tag}


def convert_dns(config: JsonDict) -> JsonDict:
    dns = config.get("dns") or {}
    if not isinstance(dns, dict) or not dns.get("enable", True):
        return {}

    servers = []
    for index, raw_server in enumerate(ensure_list(dns.get("nameserver")), start=1):
        server = convert_dns_server(raw_server, index)
        if server:
            servers.append(server)

    if not servers:
        servers.append({"type": "local", "tag": "dns-1"})

    default_dns_tag = servers[0]["tag"]
    dns_rules = []
    if dns.get("enhanced-mode") == "fake-ip":
        fakeip_server = {
            "type": "fakeip",
            "tag": "fakeip",
            "inet4_range": dns.get("fake-ip-range") or "198.18.0.0/15",
        }
        servers.append(fakeip_server)
        for item in ensure_list(dns.get("fake-ip-filter")):
            if isinstance(item, str):
                rule = domain_filter_to_rule(item, default_dns_tag)
                if rule:
                    dns_rules.append(rule)
        final = "fakeip"
    else:
        final = default_dns_tag

    return compact_dict(
        {
            "servers": servers,
            "rules": dns_rules,
            "final": final,
            "strategy": dns_strategy(config),
            "reverse_mapping": True,
        }
    )


def convert_rule(raw_rule: Any, known_tags: set[str]) -> tuple[JsonDict | None, str | None]:
    if not isinstance(raw_rule, str):
        return None, "non-string rule"

    parts = [part.strip() for part in raw_rule.split(",")]
    if len(parts) < 2:
        return None, f"invalid rule: {raw_rule}"

    rule_type = parts[0].upper()
    if rule_type == "MATCH":
        target = normalize_outbound_tag(parts[1])
        return {"__final__": target}, None

    if len(parts) < 3:
        return None, f"invalid rule: {raw_rule}"

    value = parts[1]
    target = normalize_outbound_tag(parts[2])
    if target not in known_tags:
        return None, f"rule target is not available in sing-box outbounds: {target}"

    converted: JsonDict = {"action": "route", "outbound": target}
    if rule_type == "DOMAIN":
        converted["domain"] = [value]
    elif rule_type == "DOMAIN-SUFFIX":
        converted["domain_suffix"] = [value]
    elif rule_type == "DOMAIN-KEYWORD":
        converted["domain_keyword"] = [value]
    elif rule_type in {"IP-CIDR", "IP-CIDR6"}:
        converted["ip_cidr"] = [value]
    elif rule_type == "GEOIP":
        converted["rule_set"] = [f"geoip-{value.lower()}"]
    elif rule_type == "GEOSITE":
        converted["rule_set"] = [f"geosite-{value.lower()}"]
    elif rule_type == "RULE-SET":
        return None, "RULE-SET rules require rule-provider conversion and were skipped"
    elif rule_type == "SRC-IP-CIDR":
        converted["source_ip_cidr"] = [value]
    elif rule_type == "DST-PORT":
        converted["port"] = [int(value)] if value.isdigit() else None
    elif rule_type == "PROCESS-NAME":
        converted["process_name"] = [value]
    else:
        return None, f"unsupported rule type {rule_type!r}"

    return compact_dict(converted), None


def convert_rule_sets(route_rules: list[JsonDict]) -> list[JsonDict]:
    rule_set_tags: list[str] = []
    for rule in route_rules:
        for tag in ensure_list(rule.get("rule_set")):
            if isinstance(tag, str) and tag not in rule_set_tags:
                rule_set_tags.append(tag)

    rule_sets = []
    for tag in rule_set_tags:
        rule_set_type = tag.split("-", 1)[0]
        url_template = RULE_SET_URLS.get(rule_set_type)
        if not url_template:
            continue
        rule_sets.append(
            {
                "type": "remote",
                "tag": tag,
                "format": "binary",
                "url": url_template.format(tag=tag),
                "download_detour": DIRECT_TAG,
            }
        )
    return rule_sets


def convert_route(config: JsonDict, known_tags: set[str]) -> tuple[JsonDict, list[str]]:
    route_rules = [
        {"process_name": DIRECT_PROCESS_NAMES, "action": "route", "outbound": DIRECT_TAG},
        {"ip_cidr": PRIVATE_ROUTE_CIDRS, "action": "route", "outbound": DIRECT_TAG},
        {"port": [53], "action": "hijack-dns"},
    ]
    skipped = []
    final = DIRECT_TAG

    for raw_rule in ensure_list(config.get("rules")):
        rule, reason = convert_rule(raw_rule, known_tags)
        if reason:
            skipped.append(reason)
            continue
        if not rule:
            continue
        if "__final__" in rule:
            final = rule["__final__"]
            continue
        route_rules.append(rule)

    route = compact_dict(
        {
            "rules": route_rules,
            "rule_set": convert_rule_sets(route_rules),
            "final": final if final in known_tags else DIRECT_TAG,
            "auto_detect_interface": True,
            "default_domain_resolver": compact_dict(
                {"server": "dns-1", "strategy": dns_strategy(config)}
            ),
        }
    )
    return route, skipped


def convert_experimental(config: JsonDict, output_path: Path) -> JsonDict:
    clash_api = compact_dict(
        {
            "external_controller": config.get("external-controller"),
            "external_ui": config.get("external-ui"),
            "secret": config.get("secret"),
            "default_mode": str(config.get("mode", "rule")).title(),
        }
    )
    return compact_dict(
        {
            "cache_file": {
                "enabled": True,
                "path": str(output_path.parent / "cache.db"),
                "store_fakeip": True,
            },
            "clash_api": clash_api,
        }
    )


def build_config(config: JsonDict, output_path: Path, no_tun: bool) -> tuple[JsonDict, JsonDict]:
    base_outbounds: list[JsonDict] = [
        {"type": "direct", "tag": DIRECT_TAG},
        {"type": "block", "tag": BLOCK_TAG},
    ]
    proxy_outbounds: list[JsonDict] = []
    group_outbounds: list[JsonDict] = []
    known_tags = {DIRECT_TAG, BLOCK_TAG}
    skipped_proxies = []

    for proxy in ensure_list(config.get("proxies")):
        if not isinstance(proxy, dict):
            skipped_proxies.append("non-object proxy")
            continue
        converted_outbounds, reason = convert_proxy(proxy)
        if reason:
            skipped_proxies.append(reason)
            continue
        if converted_outbounds:
            proxy_outbounds.extend(converted_outbounds)
            known_tags.update(
                outbound["tag"] for outbound in converted_outbounds if "tag" in outbound
            )

    skipped_groups = []
    for group in ensure_list(config.get("proxy-groups")):
        if not isinstance(group, dict):
            skipped_groups.append("non-object proxy group")
            continue
        outbound, reason = convert_group(group, known_tags)
        if reason:
            skipped_groups.append(reason)
            continue
        if outbound:
            group_outbounds.append(outbound)
            known_tags.add(outbound["tag"])

    outbounds = group_outbounds + base_outbounds + proxy_outbounds
    route, skipped_rules = convert_route(config, known_tags)
    sing_box_config = compact_dict(
        {
            "log": {"level": convert_log_level(config)},
            "dns": convert_dns(config),
            "inbounds": convert_inbounds(config, no_tun),
            "outbounds": outbounds,
            "route": route,
            "experimental": convert_experimental(config, output_path),
        }
    )
    stats = {
        "proxies": len(config.get("proxies", [])),
        "proxy_groups": len(config.get("proxy-groups", [])),
        "rules": len(config.get("rules", [])),
        "outbounds": len(outbounds),
        "route_rules": len(route.get("rules", [])),
        "skipped_proxies": len(skipped_proxies),
        "skipped_groups": len(skipped_groups),
        "skipped_rules": len(skipped_rules),
    }
    return sing_box_config, stats


def main() -> int:
    args = parse_args()
    config = load_yaml(args.input)
    output_path = args.output.resolve()
    sing_box_config, stats = build_config(config, output_path, args.no_tun)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(sing_box_config, file, ensure_ascii=False, indent=2)
        file.write("\n")

    print(f"Wrote sing-box config: {output_path}")
    print(
        "Converted: "
        f"{stats['proxies']} proxies, {stats['proxy_groups']} groups, "
        f"{stats['rules']} rules"
    )
    print(
        "Emitted: "
        f"{stats['outbounds']} outbounds, {stats['route_rules']} route rules"
    )
    if stats["skipped_proxies"] or stats["skipped_groups"] or stats["skipped_rules"]:
        print(
            "Skipped: "
            f"{stats['skipped_proxies']} proxies, {stats['skipped_groups']} groups, "
            f"{stats['skipped_rules']} rules",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
