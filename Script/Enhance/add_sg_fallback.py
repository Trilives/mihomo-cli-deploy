#!/usr/bin/env python3
"""Add a Singapore fallback group to a Mihomo config.

The script intentionally avoids YAML dependencies because subscription files often
contain mixed inline YAML styles. It edits only the `proxy-groups` section.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


DEFAULT_GROUP_NAME = "SG-Fallback"
DEFAULT_TEST_URL = "http://www.gstatic.com/generate_204"
DEFAULT_INTERVAL = 300
SINGAPORE_KEYWORDS = ("Singapore", "新加坡", "狮城", "🇸🇬")


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    default_config = script_dir.parent.parent / "config.yaml"

    parser = argparse.ArgumentParser(
        description="Create or update a Singapore fallback proxy group.",
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


def find_line(lines: list[str], value: str) -> int:
    for index, line in enumerate(lines):
        if line.strip() == value:
            return index
    raise ValueError(f"Missing required section: {value}")


def extract_proxy_name(line: str) -> str | None:
    match = re.search(r"(?:^\s*-\s*\{|^\s*-\s*)name:\s*([^,}\n]+)", line)
    if not match:
        return None
    return match.group(1).strip().strip('"\'')


def is_singapore_proxy(name: str) -> bool:
    upper_name = name.upper()
    return any(keyword.upper() in upper_name for keyword in SINGAPORE_KEYWORDS)


def collect_singapore_proxies(lines: list[str]) -> list[str]:
    proxies_index = find_line(lines, "proxies:")
    groups_index = find_line(lines, "proxy-groups:")
    names: list[str] = []

    for line in lines[proxies_index + 1 : groups_index]:
        name = extract_proxy_name(line)
        if name and is_singapore_proxy(name) and name not in names:
            names.append(name)

    if not names:
        raise ValueError("No Singapore proxies found in the proxies section.")
    return names


def quote_yaml(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_fallback_group(name: str, proxies: list[str], url: str, interval: int) -> list[str]:
    group = [
        f"  - name: {name}",
        "    type: fallback",
        f"    url: {url}",
        f"    interval: {interval}",
        "    proxies:",
    ]
    group.extend(f"      - {quote_yaml(proxy)}" for proxy in proxies)
    return group


def group_name_matches(line: str, group_name: str) -> bool:
    match = re.match(r"\s*-\s*name:\s*(.+?)\s*$", line)
    if not match:
        return False
    return match.group(1).strip().strip('"\'') == group_name


def remove_existing_group(lines: list[str], group_name: str) -> list[str]:
    start = next((index for index, line in enumerate(lines) if group_name_matches(line, group_name)), None)
    if start is None:
        return lines

    end = start + 1
    while end < len(lines) and not re.match(r"\s{2}-\s*name:\s*", lines[end]):
        end += 1
    return lines[:start] + lines[end:]


def first_proxy_group_bounds(lines: list[str]) -> tuple[int, int, int]:
    groups_index = find_line(lines, "proxy-groups:")
    start = groups_index + 1
    while start < len(lines) and not re.match(r"\s{2}-\s*name:\s*", lines[start]):
        start += 1
    if start >= len(lines):
        raise ValueError("No proxy group found under proxy-groups.")

    end = start + 1
    while end < len(lines) and not re.match(r"\s{2}-\s*name:\s*", lines[end]):
        end += 1

    proxies_line = next(
        (index for index in range(start, end) if lines[index].strip() == "proxies:"),
        None,
    )
    if proxies_line is None:
        raise ValueError("The first proxy group has no proxies list.")
    return start, end, proxies_line


def ensure_group_in_first_selector(lines: list[str], group_name: str) -> list[str]:
    _, group_end, proxies_line = first_proxy_group_bounds(lines)
    item = f"      - {group_name}"

    if any(line.strip() == f"- {group_name}" for line in lines[proxies_line + 1 : group_end]):
        return lines
    return lines[: proxies_line + 1] + [item] + lines[proxies_line + 1 :]


def insert_fallback_group(lines: list[str], fallback_group: list[str]) -> list[str]:
    _, first_group_end, _ = first_proxy_group_bounds(lines)
    return lines[:first_group_end] + fallback_group + lines[first_group_end:]


def update_config(config_path: Path, group_name: str, url: str, interval: int) -> None:
    original_text = config_path.read_text(encoding="utf-8")
    trailing_newline = original_text.endswith("\n")
    lines = original_text.splitlines()

    singapore_proxies = collect_singapore_proxies(lines)
    fallback_group = build_fallback_group(group_name, singapore_proxies, url, interval)

    lines = remove_existing_group(lines, group_name)
    lines = ensure_group_in_first_selector(lines, group_name)
    lines = insert_fallback_group(lines, fallback_group)

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
