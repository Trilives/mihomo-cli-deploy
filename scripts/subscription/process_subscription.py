#!/usr/bin/env python3
import argparse
import base64
import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

try:
    import yaml
except ImportError as exc:
    print("[ERROR] Missing dependency: PyYAML (python3-yaml).", file=sys.stderr)
    raise SystemExit(2) from exc


EXCLUDED_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bHK\b",
        r"hong\s*kong",
        r"香港",
        r"🇭🇰",
        r"\bhk\d*\b",
        r"\bTW\b",
        r"tai\s*wan",
        r"台湾",
        r"台灣",
        r"🇹🇼",
        r"\btw\d*\b",
    ]
]


def b64_decode_loose(text: str) -> str:
    payload = re.sub(r"\s+", "", text.strip())
    if not payload:
        return ""
    padding = "=" * ((4 - len(payload) % 4) % 4)
    raw = base64.urlsafe_b64decode((payload + padding).encode("utf-8"))
    return raw.decode("utf-8", errors="ignore")


def detect_format(raw: str):
    # Try clash yaml first.
    try:
        obj = yaml.safe_load(raw)
        if isinstance(obj, dict) and ("proxies" in obj or "proxy-providers" in obj):
            return "clash", obj
    except Exception:
        pass

    # Then try base64 subscription.
    try:
        decoded = b64_decode_loose(raw)
    except Exception:
        decoded = ""

    if decoded and re.search(r"^(ss|vmess|trojan|vless|hysteria2?|hy2)://", decoded, re.MULTILINE):
        return "base", decoded

    # Some providers return plain link list without base64 wrapper.
    if re.search(r"^(ss|vmess|trojan|vless|hysteria2?|hy2)://", raw, re.MULTILINE):
        return "base", raw

    raise ValueError("Unable to detect subscription format (clash/base64-links).")


def normalize_name(name: str, fallback: str) -> str:
    if name and isinstance(name, str) and name.strip():
        return name.strip()
    return fallback


def parse_ss_link(link: str, idx: int):
    rest = link[len("ss://") :]
    fragment = ""
    if "#" in rest:
        rest, fragment = rest.split("#", 1)
    name = unquote(fragment) if fragment else f"ss-{idx}"

    # SIP002: base64(method:password)@host:port
    if "@" in rest and ":" in rest:
        userinfo, hostport = rest.rsplit("@", 1)
        if ":" in userinfo:
            method, password = userinfo.split(":", 1)
        else:
            decoded = b64_decode_loose(userinfo)
            method, password = decoded.split(":", 1)
    else:
        decoded = b64_decode_loose(rest.split("?", 1)[0])
        left, hostport = decoded.rsplit("@", 1)
        method, password = left.split(":", 1)

    if ":" not in hostport:
        raise ValueError("invalid ss host:port")
    server, port = hostport.rsplit(":", 1)
    return {
        "name": normalize_name(name, f"ss-{idx}"),
        "type": "ss",
        "server": server,
        "port": int(port),
        "cipher": method,
        "password": password,
    }


def parse_vmess_link(link: str, idx: int):
    payload = link[len("vmess://") :]
    data = json.loads(b64_decode_loose(payload))
    tls = str(data.get("tls", "")).lower() in {"tls", "true", "1"}
    network = data.get("net") or "tcp"
    proxy = {
        "name": normalize_name(data.get("ps"), f"vmess-{idx}"),
        "type": "vmess",
        "server": data["add"],
        "port": int(data["port"]),
        "uuid": data["id"],
        "alterId": int(data.get("aid", 0)),
        "cipher": "auto",
        "network": network,
    }
    if tls:
        proxy["tls"] = True
    host = data.get("host")
    path = data.get("path")
    if host:
        proxy["servername"] = host
    if network == "ws":
        if path:
            proxy["ws-opts"] = {"path": path}
            if host:
                proxy["ws-opts"]["headers"] = {"Host": host}
    return proxy


def parse_trojan_link(link: str, idx: int):
    u = urlparse(link)
    query = parse_qs(u.query)
    name = normalize_name(unquote(u.fragment), f"trojan-{idx}")
    proxy = {
        "name": name,
        "type": "trojan",
        "server": u.hostname,
        "port": int(u.port or 443),
        "password": unquote(u.username or ""),
    }
    sni = query.get("sni", [None])[0]
    if sni:
        proxy["sni"] = sni
    if query.get("allowInsecure", ["0"])[0] in {"1", "true"}:
        proxy["skip-cert-verify"] = True
    return proxy


def parse_vless_link(link: str, idx: int):
    u = urlparse(link)
    query = parse_qs(u.query)
    name = normalize_name(unquote(u.fragment), f"vless-{idx}")
    proxy = {
        "name": name,
        "type": "vless",
        "server": u.hostname,
        "port": int(u.port or 443),
        "uuid": unquote(u.username or ""),
        "network": query.get("type", ["tcp"])[0],
        "udp": True,
    }
    tls_mode = query.get("security", [""])[0]
    if tls_mode in {"tls", "reality"}:
        proxy["tls"] = True
    sni = query.get("sni", [None])[0]
    if sni:
        proxy["servername"] = sni
    return proxy


def parse_link(line: str, idx: int):
    if line.startswith("ss://"):
        return parse_ss_link(line, idx)
    if line.startswith("vmess://"):
        return parse_vmess_link(line, idx)
    if line.startswith("trojan://"):
        return parse_trojan_link(line, idx)
    if line.startswith("vless://"):
        return parse_vless_link(line, idx)
    return None


def collect_proxies_from_links(text: str):
    proxies = []
    skipped = 0
    for idx, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            proxy = parse_link(line, idx)
            if proxy:
                proxies.append(proxy)
            else:
                skipped += 1
        except Exception:
            skipped += 1
    return proxies, skipped


def is_excluded_node(proxy: dict) -> bool:
    text = f"{proxy.get('name', '')} {proxy.get('server', '')}"
    return any(p.search(text) for p in EXCLUDED_PATTERNS)


def ensure_group(groups, name, group_type, proxies):
    for g in groups:
        if g.get("name") == name:
            g["type"] = group_type
            g["proxies"] = list(proxies)
            if group_type == "url-test":
                g.setdefault("url", "http://www.gstatic.com/generate_204")
                g.setdefault("interval", 300)
                g.setdefault("tolerance", 50)
            if group_type == "fallback":
                g.setdefault("url", "http://www.gstatic.com/generate_204")
                g.setdefault("interval", 300)
            return

    new_group = {
        "name": name,
        "type": group_type,
        "proxies": list(proxies),
    }
    if group_type == "url-test":
        new_group.update(
            {
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "tolerance": 50,
            }
        )
    if group_type == "fallback":
        new_group.update({"url": "http://www.gstatic.com/generate_204", "interval": 300})
    groups.append(new_group)


def upsert_groups(cfg: dict, proxy_names: list, clean_names: list):
    groups = cfg.setdefault("proxy-groups", [])
    ensure_group(groups, "♻️ 自动选择", "url-test", clean_names)
    ensure_group(groups, "🔁 Fallback", "fallback", clean_names)

    # Ensure selector includes the two groups for easy switching.
    for g in groups:
        if g.get("type") == "select":
            candidates = g.setdefault("proxies", [])
            for item in ["♻️ 自动选择", "🔁 Fallback"]:
                if item not in candidates:
                    candidates.insert(0, item)
            break


def build_config(template_cfg: dict, proxies: list):
    out = deepcopy(template_cfg)
    out["proxies"] = proxies
    proxy_names = [p.get("name", "") for p in proxies if p.get("name")]
    clean_names = [p.get("name", "") for p in proxies if p.get("name") and not is_excluded_node(p)]

    if not clean_names:
        clean_names = proxy_names[:]

    upsert_groups(out, proxy_names, clean_names)
    return out, len(proxy_names), len(clean_names)


def main():
    parser = argparse.ArgumentParser(description="Process subscription into mihomo config")
    parser.add_argument("--input", required=True, help="Downloaded subscription file")
    parser.add_argument("--template", help="Template config path")
    parser.add_argument("--output", help="Output config path")
    parser.add_argument("--detect-only", action="store_true", help="Only detect and print format")
    args = parser.parse_args()

    raw = Path(args.input).read_text(encoding="utf-8", errors="ignore")
    fmt, payload = detect_format(raw)
    if args.detect_only:
        print(fmt)
        return

    if not args.template or not args.output:
        raise SystemExit("[ERROR] --template and --output are required unless --detect-only is used.")

    template_cfg = yaml.safe_load(Path(args.template).read_text(encoding="utf-8", errors="ignore"))
    if not isinstance(template_cfg, dict):
        raise SystemExit("[ERROR] Template config is invalid.")

    if fmt == "clash":
        src_cfg = payload
        proxies = src_cfg.get("proxies", []) if isinstance(src_cfg, dict) else []
        if not isinstance(proxies, list):
            proxies = []
        skipped = 0
    else:
        proxies, skipped = collect_proxies_from_links(payload)

    proxies = [p for p in proxies if isinstance(p, dict) and p.get("name") and p.get("server")]
    if not proxies:
        raise SystemExit("[ERROR] No valid proxies parsed from subscription.")

    out_cfg, total, clean_count = build_config(template_cfg, proxies)
    Path(args.output).write_text(
        yaml.safe_dump(out_cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    print(f"[INFO] Format detected: {fmt}")
    print(f"[INFO] Proxies parsed: {total}")
    if skipped:
        print(f"[INFO] Skipped unsupported links: {skipped}")
    print(f"[INFO] Non-HK/TW proxies in auto/fallback: {clean_count}")


if __name__ == "__main__":
    main()
