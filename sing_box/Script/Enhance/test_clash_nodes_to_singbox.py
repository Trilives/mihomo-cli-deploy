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
            cn_domain_suffixes=["local.example"],
            local_bypass_domains=["router.local"],
            route_exclude_ip_cidrs=["192.0.2.0/24"],
            bypass_process_names=["easytier-custom"],
            easytier_bypass_domains=["easytier.example"],
            easytier_bypass_ip_cidrs=["203.0.113.10/32"],
        )

        dns = converter.build_dns(custom_config)
        route = converter.build_route("Proxy", has_sg_auto=False, custom_config=custom_config)
        tun_inbound = converter.build_inbounds(custom_config)[0]

        self.assertIn({"domain": ["router.local"], "server": "local"}, dns["rules"])
        self.assertIn({"domain": ["easytier.example"], "server": "local"}, dns["rules"])
        self.assertIn({"domain_suffix": ["ai.example"], "server": "remote"}, dns["rules"])
        self.assertEqual(tun_inbound["route_exclude_address"], ["192.0.2.0/24", "203.0.113.10/32"])
        self.assertIn(
            {"process_name": ["easytier-custom"], "action": "route", "outbound": "DIRECT"},
            route["rules"],
        )
        self.assertIn(
            {"domain": ["easytier.example"], "action": "route", "outbound": "DIRECT"},
            route["rules"],
        )
        self.assertIn(
            {"ip_cidr": ["203.0.113.10/32"], "action": "route", "outbound": "DIRECT"},
            route["rules"],
        )

    def test_resolved_easytier_ips_are_added_to_direct_route(self) -> None:
        custom_config = converter.CustomConfig(
            ai_domain_suffixes=converter.AI_DOMAIN_SUFFIXES,
            cn_domain_suffixes=converter.CN_DOMAIN_SUFFIXES,
            local_bypass_domains=converter.LOCAL_BYPASS_DOMAINS,
            route_exclude_ip_cidrs=converter.ROUTE_EXCLUDE_IP_CIDRS,
            bypass_process_names=converter.BYPASS_PROCESS_NAMES,
            easytier_bypass_domains=["easytier.example"],
            easytier_bypass_ip_cidrs=["203.0.113.10/32"],
        )

        route = converter.build_route(
            "Proxy",
            has_sg_auto=False,
            custom_config=custom_config,
            easytier_resolved_ip_cidrs=["203.0.113.10/32", "2001:db8::1/128"],
        )

        self.assertIn(
            {"ip_cidr": ["203.0.113.10/32", "2001:db8::1/128"], "action": "route", "outbound": "DIRECT"},
            route["rules"],
        )

    def test_resolved_easytier_ips_are_added_to_tun_route_excludes(self) -> None:
        custom_config = converter.CustomConfig(
            ai_domain_suffixes=converter.AI_DOMAIN_SUFFIXES,
            cn_domain_suffixes=converter.CN_DOMAIN_SUFFIXES,
            local_bypass_domains=converter.LOCAL_BYPASS_DOMAINS,
            route_exclude_ip_cidrs=["192.0.2.0/24"],
            bypass_process_names=converter.BYPASS_PROCESS_NAMES,
            easytier_bypass_domains=["easytier.example"],
            easytier_bypass_ip_cidrs=["203.0.113.10/32"],
        )

        tun_inbound = converter.build_inbounds(custom_config, ["203.0.113.10/32", "2001:db8::1/128"])[0]

        self.assertEqual(
            tun_inbound["route_exclude_address"],
            ["192.0.2.0/24", "203.0.113.10/32", "2001:db8::1/128"],
        )


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
                        "easytier_bypass_domains": ["easytier.example"],
                    }
                ),
                encoding="utf-8",
            )

            custom_config = converter.load_custom_config(config_path)

            self.assertEqual(custom_config.ai_domain_suffixes, ["ai.example"])
            self.assertEqual(custom_config.cn_domain_suffixes, converter.CN_DOMAIN_SUFFIXES)
            self.assertEqual(custom_config.easytier_bypass_domains, ["easytier.example"])

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
                    "sg_count": 0,
                    "auto_count": 1,
                    "proxy_default": "Auto",
                    "ai_default": "Auto",
                },
            )

        self.assertNotIn(sensitive_tag, output.getvalue())


if __name__ == "__main__":
    unittest.main()
