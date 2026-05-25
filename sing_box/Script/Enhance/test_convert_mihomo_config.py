from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parent
    / "convert_mihomo_config.py"
)

spec = importlib.util.spec_from_file_location("convert_mihomo_config", SCRIPT_PATH)
assert spec is not None
converter = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(converter)


class ConvertMihomoConfigTest(unittest.TestCase):
    def test_converts_vmess_with_tls_and_websocket_transport(self) -> None:
        outbounds, reason = converter.convert_proxy(
            {
                "name": "vmess-ws",
                "type": "vmess",
                "server": "example.com",
                "port": 443,
                "uuid": "00000000-0000-0000-0000-000000000000",
                "cipher": "auto",
                "tls": True,
                "servername": "sni.example.com",
                "client-fingerprint": "chrome",
                "network": "ws",
                "ws-opts": {"path": "/ws", "headers": {"Host": "host.example.com"}},
            }
        )

        self.assertIsNone(reason)
        self.assertEqual(outbounds[0]["type"], "vmess")
        self.assertEqual(outbounds[0]["tls"]["server_name"], "sni.example.com")
        self.assertEqual(outbounds[0]["tls"]["utls"]["fingerprint"], "chrome")
        self.assertEqual(outbounds[0]["transport"]["type"], "ws")
        self.assertEqual(outbounds[0]["transport"]["headers"]["Host"], ["host.example.com"])

    def test_converts_geoip_to_remote_rule_set(self) -> None:
        route, skipped = converter.convert_route(
            {"rules": ["GEOIP,CN,DIRECT,no-resolve", "MATCH,DIRECT"]},
            {converter.DIRECT_TAG, converter.BLOCK_TAG},
        )

        self.assertEqual(skipped, [])
        self.assertEqual(route["rules"][2]["rule_set"], ["geoip-cn"])
        self.assertEqual(route["rule_set"][0]["tag"], "geoip-cn")
        self.assertEqual(route["rule_set"][0]["format"], "binary")

    def test_skips_custom_rule_set_without_provider_conversion(self) -> None:
        route, skipped = converter.convert_route(
            {"rules": ["RULE-SET,custom,DIRECT", "MATCH,DIRECT"]},
            {converter.DIRECT_TAG, converter.BLOCK_TAG},
        )

        self.assertEqual(len(skipped), 1)
        self.assertNotIn("rule_set", route)

    def test_defaults_info_log_level_to_warning(self) -> None:
        self.assertEqual(converter.convert_log_level({"log-level": "info"}), "warning")
        self.assertEqual(converter.convert_log_level({}), "warning")
        self.assertEqual(converter.convert_log_level({"log-level": "debug"}), "debug")


if __name__ == "__main__":
    unittest.main()
