import tempfile
import unittest
from pathlib import Path

from mihomo_deploy import customize, yamlmini


SAMPLE = """\
proxies:
  - name: SG-01
    type: ss
    server: sg.example.com
    port: 443
    cipher: aes-256-gcm
    password: pw
  - name: HK-01
    type: ss
    server: hk.example.com
    port: 443
    cipher: aes-256-gcm
    password: pw
proxy-groups:
  - name: Proxy
    type: select
    proxies:
      - SG-01
      - HK-01
rules:
  - MATCH,Proxy
"""


class CustomizeTest(unittest.TestCase):
    def test_runtime_settings_and_region_groups(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.yaml"
            path.write_text(SAMPLE, "utf-8")
            cfg = dict(customize.DEFAULTS)
            cfg.update({"enable_tun": True, "allow_lan": False})

            customize.ensure_runtime_settings(path, cfg)
            changed = customize.add_region_groups(path, cfg)

            self.assertTrue(changed)
            data = yamlmini.load(path.read_text("utf-8"))
            self.assertEqual(data["allow-lan"], False)
            self.assertEqual(data["external-controller"], "127.0.0.1:9090")
            self.assertTrue(data["tun"]["enable"])
            names = [g["name"] for g in data["proxy-groups"]]
            self.assertIn("SG-Auto", names)
            self.assertIn("HK-Fallback", names)


if __name__ == "__main__":
    unittest.main()
