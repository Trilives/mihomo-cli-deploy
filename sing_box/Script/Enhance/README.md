# sing-box Enhance Scripts

该目录用于放置 sing-box 配置增强和转换脚本。目前主要脚本是 `clash_nodes_to_singbox.py`，用于从 Clash/Mihomo 的 `config.yaml` 提取代理节点，并生成可直接校验的 sing-box TUN 配置。

## 文件说明

- `clash_nodes_to_singbox.py`：转换 Clash/Mihomo 节点为 sing-box `config.json`。
- `clash_nodes_to_singbox_config.json`：转换脚本的自定义配置文件，用于调整 DNS、路由、直连进程和 easytier 过滤规则。
- `test_clash_nodes_to_singbox.py`：转换脚本的单元测试。

## 基本用法

```bash
./sing_box/Script/Enhance/clash_nodes_to_singbox.py
```

默认输入输出：

- 输入：`./config.yaml`
- 输出：`./sing_box/config.json`
- 自定义配置：`./sing_box/Script/Enhance/clash_nodes_to_singbox_config.json`

也可以显式指定路径：

```bash
./sing_box/Script/Enhance/clash_nodes_to_singbox.py ./config.yaml ./sing_box/config.json
```

指定自定义配置文件：

```bash
./sing_box/Script/Enhance/clash_nodes_to_singbox.py --custom-config ./sing_box/Script/Enhance/clash_nodes_to_singbox_config.json
```

## 自定义配置

`clash_nodes_to_singbox_config.json` 支持以下字段：

- `ai_domain_suffixes`：走 `AI` 出站的域名后缀。
- `cn_domain_suffixes`：本地 DNS 和 `DIRECT` 路由的国内域名后缀。
- `local_bypass_domains`：本地直连域名。
- `route_exclude_ip_cidrs`：TUN 自动路由排除网段，同时会生成直连路由规则。
- `bypass_process_names`：直连进程名，例如 `easytier`、`tailscaled`。
- `easytier_bypass_domains`：需要过滤直连的 easytier 服务器域名。
- `easytier_bypass_ip_cidrs`：手动补充的 easytier 服务器 IP CIDR。

## easytier 直连

脚本会读取 `easytier_bypass_domains`，自动解析域名 IP，并把结果转换为精确 CIDR：

- IPv4 会生成 `/32`
- IPv6 会生成 `/128`

这些 CIDR 会被加入 sing-box 路由规则并走 `DIRECT`。域名本身也会加入本地 DNS 和直连路由规则，避免 TUN 模式下 easytier 服务器流量被代理或 DNS 劫持。

如果域名解析失败，脚本只会输出 warning，并继续生成配置。

## 校验

运行单元测试：

```bash
python3 -m unittest sing_box.Script.Enhance.test_clash_nodes_to_singbox
```

生成配置后校验 sing-box 配置：

```bash
./sing_box/sing-box check -c ./sing_box/config.json
```

如果本地没有 `./sing_box/sing-box`，可以使用系统安装的 `sing-box`：

```bash
sing-box check -c ./sing_box/config.json
```

## 注意事项

- 不要提交包含订阅地址、节点密码、token 或其他敏感信息的生成配置。
- 修改 TUN、DNS 或路由相关字段后，建议先运行 `sing-box check`，确认配置无误后再启动服务。
- `route_exclude_ip_cidrs` 不应盲目加入 `172.16.0.0/12`，因为当前 TUN DNS 地址使用了 `172.19.0.2` 所在网段。
