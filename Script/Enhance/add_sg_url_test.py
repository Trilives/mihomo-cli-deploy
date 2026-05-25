#!/usr/bin/env python3
"""Add a Singapore url-test group to a Mihomo config.

The script intentionally avoids YAML dependencies because subscription files often
contain mixed inline YAML styles. It edits only the `proxy-groups` section.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from add_sg_fallback import (
    DEFAULT_INTERVAL,
    DEFAULT_TEST_URL,
    collect_singapore_proxies,
    ensure_group_in_first_selector,
    insert_fallback_group,
    quote_yaml,
    remove_existing_group,
)


DEFAULT_GROUP_NAME = "SG-UrlTest"


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    default_config = script_dir.parent.parent / "config.yaml"

    parser = argparse.ArgumentParser(
        description="Create or update a Singapore url-test proxy group.",
    )
    parser.add_argument(
        "config",
        nargs="?",
        default=default_config,
        type=Path,
        help="Path to config.yaml. Defaults to repository config.yaml.",
    )
    parser.add_argument("--group", default=DEFAULT_GROUP_NAME, help="Url-test group name.")
    parser.add_argument("--url", default=DEFAULT_TEST_URL, help="Health check URL.")
    parser.add_argument(
        "--interval",
        default=DEFAULT_INTERVAL,
        type=int,
        help="Health check interval in seconds.",
    )
    return parser.parse_args()


def build_url_test_group(name: str, proxies: list[str], url: str, interval: int) -> list[str]:
    group = [
        f"  - name: {name}",
        "    type: url-test",
        f"    url: {url}",
        f"    interval: {interval}",
        "    proxies:",
    ]
    group.extend(f"      - {quote_yaml(proxy)}" for proxy in proxies)
    return group


def update_config(config_path: Path, group_name: str, url: str, interval: int) -> None:
    original_text = config_path.read_text(encoding="utf-8")
    trailing_newline = original_text.endswith("\n")
    lines = original_text.splitlines()

    singapore_proxies = collect_singapore_proxies(lines)
    url_test_group = build_url_test_group(group_name, singapore_proxies, url, interval)

    lines = remove_existing_group(lines, group_name)
    lines = ensure_group_in_first_selector(lines, group_name)
    lines = insert_fallback_group(lines, url_test_group)

    updated_text = "\n".join(lines)
    if trailing_newline:
        updated_text += "\n"
    config_path.write_text(updated_text, encoding="utf-8")

    print(f"Updated {config_path}")
    print(f"Group: {group_name}")
    print(f"Singapore proxies: {len(singapore_proxies)}")


def main() -> None:
    args = parse_args()
    update_config(args.config, args.group, args.url, args.interval)


if __name__ == "__main__":
    main()
