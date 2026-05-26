from __future__ import annotations

import io
import importlib.util
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent / "clash_nodes_to_singbox.py"

spec = importlib.util.spec_from_file_location("clash_nodes_to_singbox", SCRIPT_PATH)
assert spec is not None
converter = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(converter)


class ClashNodesToSingboxDnsTest(unittest.TestCase):
    def test_non_cn_domains_use_proxied_remote_dns_by_default(self) -> None:
        dns = converter.build_dns()

        self.assertEqual(dns["final"], "remote")
        self.assertIn({"domain": ["localhost"], "server": "local"}, dns["rules"])
        self.assertIn({"domain_suffix": converter.CN_DOMAIN_SUFFIXES, "server": "local"}, dns["rules"])

    def test_node_bootstrap_resolution_stays_on_local_dns(self) -> None:
        route = converter.build_route("Proxy", has_sg_auto=False)

        self.assertEqual(route["default_domain_resolver"], "local")

    def test_tun_dns_subnet_is_not_excluded_from_tun_routing(self) -> None:
        tun_inbound = converter.build_inbounds()[0]

        self.assertNotIn("172.16.0.0/12", tun_inbound["route_exclude_address"])
        self.assertIn(
            {"protocol": "dns", "action": "hijack-dns"}, converter.build_route("Proxy", False)["rules"]
        )

    def test_windows_desktop_tun_has_conservative_mtu_and_direct_networks(self) -> None:
        tun_inbound = converter.build_inbounds()[0]

        self.assertEqual(tun_inbound["mtu"], 1400)
        for cidr in (
            "10.126.126.0/24",
            "10.14.14.0/24",
            "100.64.0.0/10",
            "192.168.0.0/16",
        ):
            self.assertIn(cidr, tun_inbound["route_exclude_address"])

    def test_custom_config_overrides_dns_and_route_values(self) -> None:
        custom_config = converter.CustomConfig(
            ai_domain_suffixes=["ai.example"],
            streaming_domain_suffixes=["stream.example"],
            cn_domain_suffixes=["local.example"],
            local_bypass_domains=["router.local"],
            route_exclude_ip_cidrs=["192.0.2.0/24"],
            bypass_process_names=["tailscaled-custom"],
            tun_exclude_uids=[997],
        )

        dns = converter.build_dns(custom_config)
        route = converter.build_route("Proxy", has_sg_auto=False, custom_config=custom_config)
        tun_inbound = converter.build_inbounds(custom_config)[0]

        self.assertIn({"domain": ["router.local"], "server": "local"}, dns["rules"])
        self.assertIn({"domain_suffix": ["ai.example"], "server": "remote"}, dns["rules"])
        self.assertIn({"domain_suffix": ["stream.example"], "server": "remote"}, dns["rules"])
        self.assertEqual(tun_inbound["route_exclude_address"], ["192.0.2.0/24"])
        self.assertEqual(tun_inbound["exclude_uid"], [997])
        self.assertIn(
            {"process_name": ["tailscaled-custom"], "action": "route", "outbound": "DIRECT"},
            route["rules"],
        )
        self.assertIn(
            {"domain_suffix": ["stream.example"], "action": "route", "outbound": "Streaming"},
            route["rules"],
        )

    def test_sg_fallback_and_ai_can_select_proxy(self) -> None:
        nodes = [
            {"type": "direct", "tag": "Traffic: 1 GB | 20 GB"},
            {"type": "direct", "tag": "Expire: 2027-01-28"},
            {"type": "direct", "tag": "SG Node"},
            {"type": "direct", "tag": "SG 实验 Node"},
            {"type": "direct", "tag": "US Node"},
        ]

        outbounds, info = converter.build_outbounds(nodes, ["SG"])
        by_tag = {outbound["tag"]: outbound for outbound in outbounds}

        self.assertTrue(info["has_sg_fallback"])
        self.assertEqual(by_tag["SG-Fallback"]["outbounds"], ["SG Node"])
        self.assertEqual(by_tag["SG-Auto"]["outbounds"], ["SG Node"])
        self.assertEqual(by_tag["Auto"]["outbounds"], ["SG Node", "SG 实验 Node", "US Node"])
        self.assertEqual(by_tag["AI"]["outbounds"][0], "Proxy")
        self.assertEqual(by_tag["Streaming"]["outbounds"][0], "Proxy")
        self.assertNotIn("AI", by_tag["Proxy"]["outbounds"])
        self.assertNotIn("Streaming", by_tag["Proxy"]["outbounds"])
        self.assertEqual(by_tag["Proxy"]["outbounds"][:3], ["SG-Auto", "SG-Fallback", "Auto"])
        self.assertEqual(by_tag["Fallback"]["outbounds"], ["Proxy", "Auto", "DIRECT"])
        self.assertNotIn("Traffic: 1 GB | 20 GB", by_tag["Proxy"]["outbounds"])
        self.assertNotIn("Expire: 2027-01-28", by_tag["Proxy"]["outbounds"])
        outbound_tags = [outbound["tag"] for outbound in outbounds]
        self.assertEqual(outbound_tags[-1], "Fallback")


class ClashNodesToSingboxErrorHandlingTest(unittest.TestCase):
    def test_load_yaml_reports_missing_and_invalid_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing.yaml"
            invalid_path = Path(temp_dir) / "invalid.yaml"
            invalid_path.write_text("proxies: [", encoding="utf-8")

            with self.assertRaisesRegex(converter.ConversionError, "Failed to read input file"):
                converter.load_yaml(missing_path)
            with self.assertRaisesRegex(converter.ConversionError, "Invalid YAML"):
                converter.load_yaml(invalid_path)

    def test_load_custom_config_reads_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "custom.json"
            config_path.write_text(
                json.dumps(
                    {
                        "ai_domain_suffixes": ["ai.example", "ai.example"],
                        "streaming_domain_suffixes": ["stream.example"],
                        "tun_exclude_uids": [997, "997"],
                    }
                ),
                encoding="utf-8",
            )

            custom_config = converter.load_custom_config(config_path)

        self.assertEqual(custom_config.ai_domain_suffixes, ["ai.example"])
        self.assertEqual(custom_config.streaming_domain_suffixes, ["stream.example"])
        self.assertEqual(custom_config.cn_domain_suffixes, converter.CN_DOMAIN_SUFFIXES)
        self.assertEqual(custom_config.tun_exclude_uids, [997])

    def test_output_path_must_be_below_sing_box_directory(self) -> None:
        allowed_path = converter.SING_BOX_DIR / "generated-test.json"

        self.assertEqual(converter.validate_output_path(allowed_path), allowed_path.resolve())
        with self.assertRaisesRegex(converter.ConversionError, "inside the sing_box directory"):
            converter.validate_output_path(Path("/tmp/outside-sing-box.json"))

    def test_json_serialization_failure_does_not_create_output_file(self) -> None:
        with tempfile.TemporaryDirectory(dir=converter.SING_BOX_DIR) as temp_dir:
            output_path = Path(temp_dir) / "config.json"

            with self.assertRaisesRegex(converter.ConversionError, "serialize generated JSON"):
                converter.write_json_config({"bad": object()}, output_path)
            self.assertFalse(output_path.exists())

    def test_json_write_failure_is_reported_cleanly(self) -> None:
        with tempfile.TemporaryDirectory(dir=converter.SING_BOX_DIR) as temp_dir:
            with self.assertRaisesRegex(converter.ConversionError, "write output JSON"):
                converter.write_json_config({}, Path(temp_dir))

    def test_summary_does_not_print_a_sensitive_node_tag(self) -> None:
        sensitive_tag = "00000000-0000-0000-0000-secret-token"
        output = io.StringIO()

        with redirect_stdout(output):
            converter.print_summary(
                Path("config.yaml"),
                Path("sing_box/config.json"),
                1,
                [{"type": "vmess", "tag": sensitive_tag}],
                converter.Counter(),
                {
                    "has_sg_auto": False,
                    "has_sg_fallback": False,
                    "sg_count": 0,
                    "auto_count": 1,
                    "proxy_default": "Auto",
                    "ai_default": "Auto",
                    "streaming_default": "Auto",
                },
            )

        self.assertNotIn(sensitive_tag, output.getvalue())


if __name__ == "__main__":
    unittest.main()
