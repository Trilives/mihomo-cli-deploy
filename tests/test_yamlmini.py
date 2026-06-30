import unittest

from mihomo_deploy import yamlmini


class YamlMiniTest(unittest.TestCase):
    def test_parse_clash_style_yaml(self) -> None:
        data = yamlmini.load(
            """
proxies:
  - {name: sg-01, type: ss, server: example.com, port: 443, udp: true}
proxy-groups:
  - name: Proxy
    type: select
    proxies: [sg-01, DIRECT]
"""
        )
        self.assertEqual(data["proxies"][0]["name"], "sg-01")
        self.assertTrue(data["proxies"][0]["udp"])
        self.assertEqual(data["proxy-groups"][0]["proxies"], ["sg-01", "DIRECT"])


if __name__ == "__main__":
    unittest.main()

