import tempfile
import unittest
from pathlib import Path

from mihomo_deploy import node_select, yamlmini


SAMPLE = """\
proxy-groups:
  - name: Proxy
    type: select
    proxies:
      - HK-01
      - SG-01
      - DIRECT
proxies:
  - name: HK-01
    type: ss
    server: hk.example.com
    port: 443
  - name: SG-01
    type: ss
    server: sg.example.com
    port: 443
"""


class NodeSelectTest(unittest.TestCase):
    def test_persist_selected_node_first(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.yaml"
            path.write_text(SAMPLE, "utf-8")
            data = yamlmini.load(path.read_text("utf-8"))
            node_select._persist_first(data, "Proxy", "SG-01", [path])
            updated = yamlmini.load(path.read_text("utf-8"))
            group = updated["proxy-groups"][0]
            self.assertEqual(group["proxies"][0], "SG-01")
            self.assertEqual(group["proxies"].count("SG-01"), 1)


if __name__ == "__main__":
    unittest.main()

