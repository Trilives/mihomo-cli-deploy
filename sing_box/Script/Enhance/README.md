# sing-box Enhance Scripts

该目录用于放置 sing-box 配置增强和转换脚本。目前主要脚本是 `clash_nodes_to_singbox.py`，用于从 Clash/Mihomo 的 `config.yaml` 提取代理节点，并生成可直接校验的 sing-box TUN 配置。

## 文件说明

- `clash_nodes_to_singbox.py`：转换 Clash/Mihomo 节点为 sing-box `config.json`。
- `clash_nodes_to_singbox_config.json`：转换脚本的自定义配置文件，用于调整 DNS、路由、直连进程和 TUN UID 排除规则。
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
- `streaming_domain_suffixes`：走 `Streaming` 出站的流媒体域名后缀。
- `cn_domain_suffixes`：本地 DNS 和 `DIRECT` 路由的国内域名后缀。
- `local_bypass_domains`：本地直连域名。
- `route_exclude_ip_cidrs`：TUN 自动路由排除网段，同时会生成直连路由规则。
- `bypass_process_names`：直连进程名，例如 `tailscaled`。
- `tun_exclude_uids`：写入 TUN 入站的 `exclude_uid`，用于让指定系统用户的流量绕过 sing-box 自动路由。

## 出站分组

脚本会根据 `--prefer` 关键词生成新加坡专用分组：

- `SG-Auto`：`urltest` 自动测速分组。
- `SG-Fallback`：同一批新加坡节点的手动选择分组。

名称包含 `实验` 的节点不会进入 `SG-Auto` 或 `SG-Fallback`，但仍保留在 `Auto` 和 `Proxy` 的完整节点列表中。`AI` 选择器默认选择 `Proxy`，也可以切换到 `SG-Auto`、`SG-Fallback`、`Auto` 或 `DIRECT`。

`Auto` 和 `Proxy` 会过滤订阅说明节点，例如 `Traffic:`、`Expire:`、`剩余流量`、`过期时间`。顶层 `outbounds` 会先保留真实节点和常用策略组，再把 `SG-Auto`、`SG-Fallback`、`Auto` 等自动/地区分组放在后面，`Fallback` 放在最后；`Proxy` 内部仍保持分组优先。

`Streaming` 是和 `AI` 类似的流媒体选择器，匹配 `streaming_domain_suffixes` 后走该组，默认选择 `Proxy`。

## EasyTier 绕过

EasyTier 的 P2P peer IP 是动态发现的，不应靠 `easytier_bypass_domains` 或手工 IP 列表长期维护。推荐做法：

- 让 EasyTier 用独立系统用户运行，例如 `easytier`。
- 添加高于 sing-box `9000+` 规则的策略路由，例如 `ip rule add pref 1000 uidrange 997-997 lookup main`。
- 在 `clash_nodes_to_singbox_config.json` 中设置 `tun_exclude_uids`，让 sing-box TUN 也显式排除 EasyTier UID。

这样可以保留 sing-box `strict_route`，同时让 EasyTier 动态 P2P 数据面稳定走物理网卡。

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
