import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mihomo_deploy import paths, yamlmini
from mihomo_deploy.subscription import manager


SAMPLE = """\
proxies:
  - name: SG-01
    type: ss
    server: sg.example.com
    port: 443
    cipher: aes-256-gcm
    password: pw
proxy-groups:
  - name: Airport
    type: select
    proxies:
      - SG-01
rules:
  - MATCH,Airport
"""


class SubscriptionManagerTest(unittest.TestCase):
    def test_default_preserves_provider_groups(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with mock.patch.object(paths, "STATE_DIR", root / "state"), \
                 mock.patch.object(paths, "SUBSCRIPTIONS_DIR", root / "state" / "subscriptions"), \
                 mock.patch.object(paths, "ACTIVE_FILE", root / "state" / "active"), \
                 mock.patch.object(paths, "CONFIG_FILE", root / "state" / "config.yaml"), \
                 mock.patch.object(paths, "LEGACY_CONFIG_FILE", root / "config.yaml"):
                with mock.patch("mihomo_deploy.subscription.fetch.direct", return_value=SAMPLE.encode()):
                    manager.add("default", "https://example.test/sub", "clash", customize_flag=False)
                data = yamlmini.load((root / "state" / "subscriptions" / "default" / "config.yaml").read_text())
                self.assertEqual([g["name"] for g in data["proxy-groups"]], ["Airport"])

    def test_custom_groups_are_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with mock.patch.object(paths, "STATE_DIR", root / "state"), \
                 mock.patch.object(paths, "SUBSCRIPTIONS_DIR", root / "state" / "subscriptions"), \
                 mock.patch.object(paths, "ACTIVE_FILE", root / "state" / "active"), \
                 mock.patch.object(paths, "CONFIG_FILE", root / "state" / "config.yaml"), \
                 mock.patch.object(paths, "LEGACY_CONFIG_FILE", root / "config.yaml"):
                with mock.patch("mihomo_deploy.subscription.fetch.direct", return_value=SAMPLE.encode()):
                    manager.add("default", "https://example.test/sub", "clash", customize_flag=True)
                data = yamlmini.load((root / "state" / "subscriptions" / "default" / "config.yaml").read_text())
                names = [g["name"] for g in data["proxy-groups"]]
                self.assertIn("SG-Auto", names)
                self.assertIn("Airport", names)


if __name__ == "__main__":
    unittest.main()

