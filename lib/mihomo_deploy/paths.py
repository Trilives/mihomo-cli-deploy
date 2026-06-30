"""统一路径常量。

运行期产物落在仓库根目录的 state/ 下；旧根目录 config.yaml / mihomo 等只作为兼容副本。
"""

from __future__ import annotations

import os
from pathlib import Path


def _detect_root() -> Path:
    env = os.environ.get("MIHOMO_DEPLOY_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[2]


ROOT = _detect_root()
TEMPLATES_DIR = ROOT / "templates"

STATE_DIR = ROOT / "state"
BIN_DIR = STATE_DIR / "bin"
MIHOMO_BIN = BIN_DIR / "mihomo"
MIHOMO_VERSION_FILE = BIN_DIR / "mihomo.version"
UI_DIR = STATE_DIR / "ui"
GEO_DIR = STATE_DIR / "geo"
DOWNLOADS_DIR = STATE_DIR / "downloads"
SUBSCRIPTIONS_DIR = STATE_DIR / "subscriptions"
ACTIVE_FILE = STATE_DIR / "active"
CONFIG_FILE = STATE_DIR / "config.yaml"
CUSTOMIZE_FILE = STATE_DIR / "customize.json"

COUNTRY_MMDB = GEO_DIR / "country.mmdb"
GEOIP_METADB = GEO_DIR / "geoip.metadb"

LEGACY_CONFIG_FILE = ROOT / "config.yaml"
LEGACY_MIHOMO_BIN = ROOT / "mihomo"
LEGACY_VERSION_FILE = ROOT / "mihomo.version"
LEGACY_UI_DIR = ROOT / "ui"
LEGACY_COUNTRY_MMDB = ROOT / "country.mmdb"
LEGACY_GEOIP_METADB = ROOT / "geoip.metadb"

ETC_DIR = Path("/etc/mihomo")


def ensure_state_dirs() -> None:
    for d in (STATE_DIR, BIN_DIR, UI_DIR, GEO_DIR, DOWNLOADS_DIR, SUBSCRIPTIONS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def subscription_dir(name: str) -> Path:
    return SUBSCRIPTIONS_DIR / name

