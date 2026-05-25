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
DNS_TAG = "dns-out"
DEFAULT_TEST_URL = "https://www.gstatic.com/generate_204"


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


def normalize_outbound_tag(tag: str) -> str:
    upper_tag = tag.upper()
    if upper_tag == "DIRECT":
        return DIRECT_TAG
    if upper_tag in {"REJECT", "REJECT-DROP"}:
        return BLOCK_TAG
    return tag


def convert_ss_plugin(proxy: JsonDict) -> tuple[str | None, str | None]:
    plugin = proxy.get("plugin")
    plugin_opts = proxy.get("plugin-opts") or {}
    if not plugin:
        return None, None

    if plugin == "obfs":
        mode = plugin_opts.get("mode", "http")
        host = plugin_opts.get("host")
        options = [f"obfs={mode}"]
        if host:
            options.append(f"obfs-host={host}")
        return "obfs-local", ";".join(options)

    if plugin == "v2ray-plugin":
        opts = []
        for key, value in plugin_opts.items():
            if isinstance(value, bool):
                if value:
                    opts.append(str(key))
            else:
                opts.append(f"{key}={value}")
        return "v2ray-plugin", ";".join(opts)

    return None, None


def convert_proxy(proxy: JsonDict) -> tuple[JsonDict | None, str | None]:
    proxy_type = proxy.get("type")
    name = proxy.get("name")
    if not isinstance(name, str):
        return None, "proxy without a string name"

    if proxy_type != "ss":
        return None, f"unsupported proxy type {proxy_type!r}: {name}"

    plugin, plugin_opts = convert_ss_plugin(proxy)
    outbound = compact_dict(
        {
            "type": "shadowsocks",
            "tag": name,
            "server": proxy.get("server"),
            "server_port": proxy.get("port"),
            "method": proxy.get("cipher"),
            "password": proxy.get("password"),
            "plugin": plugin,
            "plugin_opts": plugin_opts,
        }
    )
    return outbound, None


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
        inbound = compact_dict(
            {
                "type": "tun",
                "tag": "tun-in",
                "address": ["172.19.0.1/30"],
                "stack": tun.get("stack"),
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
        return {"type": "tls", "tag": f"dns-{index}", "server": host, "server_port": port}

    if raw_server.startswith("https://"):
        parsed = urlparse(raw_server)
        return compact_dict(
            {
                "type": "https",
                "tag": f"dns-{index}",
                "server": parsed.hostname,
                "server_port": parsed.port or 443,
                "path": parsed.path or "/dns-query",
            }
        )

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
            "strategy": "ipv4_only" if config.get("ipv6") is False or dns.get("ipv6") is False else None,
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
        converted["geoip"] = [value.lower()]
    elif rule_type == "SRC-IP-CIDR":
        converted["source_ip_cidr"] = [value]
    elif rule_type == "DST-PORT":
        converted["port"] = [int(value)] if value.isdigit() else None
    elif rule_type == "PROCESS-NAME":
        converted["process_name"] = [value]
    else:
        return None, f"unsupported rule type {rule_type!r}"

    return compact_dict(converted), None


def convert_route(config: JsonDict, known_tags: set[str]) -> tuple[JsonDict, list[str]]:
    route_rules = []
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
            "final": final if final in known_tags else DIRECT_TAG,
            "auto_detect_interface": True,
        }
    )
    return route, skipped


def convert_experimental(config: JsonDict, output_path: Path) -> JsonDict:
    clash_api = compact_dict(
        {
            "external_controller": config.get("external-controller"),
            "external_ui": config.get("external-ui"),
            "default_mode": str(config.get("mode", "rule")).title(),
            "cache_file": str(output_path.parent / "cache.db"),
        }
    )
    if not clash_api:
        return {}
    return {"clash_api": clash_api, "cache_file": {"enabled": True, "path": str(output_path.parent / "cache.db")}}


def build_config(config: JsonDict, output_path: Path, no_tun: bool) -> tuple[JsonDict, JsonDict]:
    outbounds: list[JsonDict] = [
        {"type": "direct", "tag": DIRECT_TAG},
        {"type": "block", "tag": BLOCK_TAG},
        {"type": "dns", "tag": DNS_TAG},
    ]
    known_tags = {DIRECT_TAG, BLOCK_TAG, DNS_TAG}
    skipped_proxies = []

    for proxy in ensure_list(config.get("proxies")):
        if not isinstance(proxy, dict):
            skipped_proxies.append("non-object proxy")
            continue
        outbound, reason = convert_proxy(proxy)
        if reason:
            skipped_proxies.append(reason)
            continue
        if outbound:
            outbounds.append(outbound)
            known_tags.add(outbound["tag"])

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
            outbounds.append(outbound)
            known_tags.add(outbound["tag"])

    route, skipped_rules = convert_route(config, known_tags)
    sing_box_config = compact_dict(
        {
            "log": {"level": config.get("log-level", "info")},
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
