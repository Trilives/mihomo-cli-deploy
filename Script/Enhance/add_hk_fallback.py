#!/usr/bin/env python3
"""Add a Hong Kong fallback group to a Mihomo config.

The script intentionally avoids YAML dependencies because subscription files often
contain mixed inline YAML styles. It edits only the `proxy-groups` section.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from add_sg_fallback import (
    DEFAULT_INTERVAL,
    DEFAULT_TEST_URL,
    build_fallback_group,
    ensure_group_in_first_selector,
    extract_proxy_name,
    find_line,
    insert_fallback_group,
    remove_existing_group,
)


DEFAULT_GROUP_NAME = "HK-Fallback"
HONG_KONG_KEYWORDS = ("Hong Kong", "香港", "🇭🇰", "HK")


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    default_config = script_dir.parent.parent / "config.yaml"

    parser = argparse.ArgumentParser(
        description="Create or update a Hong Kong fallback proxy group.",
    )
    parser.add_argument(
        "config",
        nargs="?",
        default=default_config,
        type=Path,
        help="Path to config.yaml. Defaults to repository config.yaml.",
    )
    parser.add_argument("--group", default=DEFAULT_GROUP_NAME, help="Fallback group name.")
    parser.add_argument("--url", default=DEFAULT_TEST_URL, help="Health check URL.")
    parser.add_argument(
        "--interval",
        default=DEFAULT_INTERVAL,
        type=int,
        help="Health check interval in seconds.",
    )
    return parser.parse_args()


def is_hong_kong_proxy(name: str) -> bool:
    upper_name = name.upper()
    return any(keyword.upper() in upper_name for keyword in HONG_KONG_KEYWORDS)


def collect_hong_kong_proxies(lines: list[str]) -> list[str]:
    proxies_index = find_line(lines, "proxies:")
    groups_index = find_line(lines, "proxy-groups:")
    names: list[str] = []

    for line in lines[proxies_index + 1 : groups_index]:
        name = extract_proxy_name(line)
        if name and is_hong_kong_proxy(name) and name not in names:
            names.append(name)

    if not names:
        raise ValueError("No Hong Kong proxies found in the proxies section.")
    return names


def update_config(config_path: Path, group_name: str, url: str, interval: int) -> None:
    original_text = config_path.read_text(encoding="utf-8")
    trailing_newline = original_text.endswith("\n")
    lines = original_text.splitlines()

    hong_kong_proxies = collect_hong_kong_proxies(lines)
    fallback_group = build_fallback_group(group_name, hong_kong_proxies, url, interval)

    lines = remove_existing_group(lines, group_name)
    lines = ensure_group_in_first_selector(lines, group_name)
    lines = insert_fallback_group(lines, fallback_group)

    updated_text = "\n".join(lines)
    if trailing_newline:
        updated_text += "\n"
    config_path.write_text(updated_text, encoding="utf-8")

    print(f"Updated {config_path}")
    print(f"Group: {group_name}")
    print(f"Hong Kong proxies: {len(hong_kong_proxies)}")


def main() -> None:
    args = parse_args()
    update_config(args.config, args.group, args.url, args.interval)


if __name__ == "__main__":
    main()
