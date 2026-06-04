#!/usr/bin/env python3
"""Enable Mihomo TUN mode and LAN dashboard settings in config.yaml.

The script intentionally avoids YAML dependencies because subscription files often
contain mixed inline YAML styles. It only edits top-level Mihomo settings.
"""

from __future__ import annotations

import argparse
import re
import secrets
from pathlib import Path


DEFAULT_CONTROLLER = "0.0.0.0:9090"
DEFAULT_EXTERNAL_UI = "ui"
DEFAULT_TUN_STACK = "gvisor"


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    default_config = script_dir.parent.parent / "config.yaml"

    parser = argparse.ArgumentParser(
        description="Enable TUN mode and LAN Web UI settings for Mihomo.",
    )
    parser.add_argument(
        "config",
        nargs="?",
        default=default_config,
        type=Path,
        help="Path to config.yaml. Defaults to repository config.yaml.",
    )
    parser.add_argument(
        "--controller",
        default=DEFAULT_CONTROLLER,
        help="external-controller listen address.",
    )
    parser.add_argument(
        "--external-ui",
        default=DEFAULT_EXTERNAL_UI,
        help="external-ui path.",
    )
    parser.add_argument(
        "--secret",
        default=None,
        help="Dashboard secret. Existing non-empty secret is preserved when omitted; missing secret is not created.",
    )
    parser.add_argument(
        "--tun-stack",
        default=DEFAULT_TUN_STACK,
        choices=("gvisor", "system", "mixed"),
        help="TUN stack.",
    )
    parser.add_argument(
        "--dashboard-only",
        action="store_true",
        help="Only enable LAN dashboard settings and skip TUN changes.",
    )
    parser.add_argument(
        "--generate-secret",
        action="store_true",
        help="Generate a random dashboard secret when one is missing.",
    )
    return parser.parse_args()


def is_top_level_key(line: str) -> bool:
    return re.match(r"^[A-Za-z0-9_-]+\s*:", line) is not None


def top_level_key(line: str) -> str | None:
    match = re.match(r"^([A-Za-z0-9_-]+)\s*:", line)
    if not match:
        return None
    return match.group(1)


def find_block(lines: list[str], key: str) -> tuple[int, int] | None:
    start = next((index for index, line in enumerate(lines) if top_level_key(line) == key), None)
    if start is None:
        return None

    end = start + 1
    while end < len(lines) and not is_top_level_key(lines[end]):
        end += 1
    return start, end


def default_insert_index(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if top_level_key(line) in {"sniffer", "dns", "proxies", "proxy-groups", "rules"}:
            return index
    return len(lines)


def replace_or_insert_block(lines: list[str], key: str, block: list[str], insert_at: int | None = None) -> list[str]:
    bounds = find_block(lines, key)
    if bounds is not None:
        start, end = bounds
        return lines[:start] + block + lines[end:]

    if insert_at is None:
        insert_at = default_insert_index(lines)
    return lines[:insert_at] + block + lines[insert_at:]


def existing_secret(lines: list[str]) -> str | None:
    bounds = find_block(lines, "secret")
    if bounds is None:
        return None

    value = lines[bounds[0]].split(":", 1)[1].strip().strip('"\'')
    return value or None


def quote_yaml(value: str) -> str:
    return '"' + value.replace('"', '\\"') + '"'


def build_tun_block(stack: str) -> list[str]:
    return [
        "tun:",
        "  enable: true",
        f"  stack: {stack}",
        "  auto-route: true",
        "  auto-detect-interface: true",
        "  dns-hijack:",
        "    - any:53",
        "    - tcp://any:53",
    ]


def update_config(
    config_path: Path,
    controller: str,
    external_ui: str,
    secret: str | None,
    tun_stack: str,
    skip_tun: bool = False,
    generate_secret: bool = False,
) -> None:
    original_text = config_path.read_text(encoding="utf-8")
    trailing_newline = original_text.endswith("\n")
    lines = original_text.splitlines()

    existing_dashboard_secret = existing_secret(lines)
    dashboard_secret = secret if secret is not None else existing_dashboard_secret
    secret_generated = False
    if dashboard_secret is None and generate_secret:
        dashboard_secret = secrets.token_hex(16)
        secret_generated = True

    for key, value in [
        ("allow-lan", "true"),
        ("external-controller", controller),
        ("external-ui", external_ui),
    ]:
        lines = replace_or_insert_block(lines, key, [f"{key}: {value}"])

    if dashboard_secret is not None:
        lines = replace_or_insert_block(lines, "secret", [f"secret: {quote_yaml(dashboard_secret)}"])

    if not skip_tun:
        tun_insert_at = next(
            (index for index, line in enumerate(lines) if top_level_key(line) in {"proxies", "proxy-groups", "rules"}),
            len(lines),
        )
        lines = replace_or_insert_block(lines, "tun", build_tun_block(tun_stack), tun_insert_at)

    updated_text = "\n".join(lines)
    if trailing_newline:
        updated_text += "\n"
    config_path.write_text(updated_text, encoding="utf-8")

    print(f"Updated {config_path}")
    print(f"external-controller: {controller}")
    print(f"external-ui: {external_ui}")
    if dashboard_secret is None:
        print("secret: unchanged (not configured)")
    elif secret_generated:
        print(f"secret: generated {dashboard_secret}")
    else:
        print("secret: preserved" if secret is None else "secret: updated")
    if not skip_tun:
        print(f"tun.stack: {tun_stack}")


def main() -> None:
    args = parse_args()
    update_config(
        args.config,
        args.controller,
        args.external_ui,
        args.secret,
        args.tun_stack,
        skip_tun=args.dashboard_only,
        generate_secret=args.generate_secret,
    )


if __name__ == "__main__":
    main()
