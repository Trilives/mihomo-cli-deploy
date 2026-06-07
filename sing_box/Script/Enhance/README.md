# sing-box Enhance Scripts

该目录用于放置 sing-box 配置增强和转换脚本。目前主要脚本是 `clash_nodes_to_singbox.py`，用于从 Clash/Mihomo 的 `config.yaml` 提取代理节点，并生成可直接校验的 sing-box TUN 配置。

## 文件说明

- `clash_nodes_to_singbox.py`：转换 Clash/Mihomo 节点为 sing-box `config.json`。
- `clash_nodes_to_singbox_config.json`：转换脚本的自定义配置文件，用于调整 DNS、路由、直连进程和 TUN UID 排除规则。

## 基本用法

```bash
./sing_box/Script/Enhance/clash_nodes_to_singbox.py
```

默认输入输出：

- 输入：`./config.yaml`
- 输出：`./sing_box/config.json`
- 自定义配置：`./sing_box/Script/Enhance/clash_nodes_to_singbox_config.json`
- CN 规则集：`./sing_box/ruleset/geosite-cn.srs` 和 `./sing_box/ruleset/geoip-cn.srs`

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
- `direct_domain_suffixes`：指定直连的域名后缀。填写后会新增一个 `Direct` 特殊直连组，并把这些域名优先路由到该组（默认 `DIRECT`，可在面板切换到 `Proxy`/`Auto`），同时让它们走本地 DNS 解析。留空（默认）则不生成该组。
- `local_bypass_domains`：本地直连域名。
- `route_exclude_ip_cidrs`：TUN 自动路由排除网段，同时会生成直连路由规则。
- `bypass_process_names`：直连进程名，例如 `tailscaled`。
- `tun_exclude_uids`：写入 TUN 入站的 `exclude_uid`，用于让指定系统用户的流量绕过 sing-box 自动路由。
- `lan_panel`：是否允许局域网访问 Clash API/Web UI。`true` 时监听 `0.0.0.0:9090` 并放行私有网络访问；`false`（默认）仅监听 `127.0.0.1:9090`。命令行 `--lan-panel` 仍可强制开启（覆盖此字段）。

## CN 规则集

转换脚本不再使用手写的 `.cn` 域名后缀列表做国内分流，而是生成 sing-box 官方推荐的 `rule_set` 配置：

- `geosite-cn`：用于国内域名 DNS 本地解析和路由直连。
- `geoip-cn`：用于国内 IP 路由直连。

规则集文件由 `./sing_box/Script/update_sing_box_core.sh` 下载自 SagerNet 维护的官方仓库：

- `SagerNet/sing-geosite`：`geosite-cn.srs`
- `SagerNet/sing-geoip`：`geoip-cn.srs`

## 每周自动更新

本仓库采用本地 `rule_set`（`type: local`），规则集启动时一次性读入，因此需要定期更新 `.srs` 文件并重启服务才能保持新鲜。`sing_box/Script/` 下提供了两个脚本来自动化这一流程：

- `update_and_redeploy.sh`：依次执行 `update_sing_box_core.sh`（更新内核、Web UI、`geosite-cn.srs`/`geoip-cn.srs`）和 `setup_sing_box_service.sh`（重装 config 并重启服务，使新内核和新规则集生效）。额外参数会透传给 `update_sing_box_core.sh`，例如 `--libc musl`。
- `setup_weekly_update_timer.sh`：安装一个 systemd timer，默认每周一 03:00 运行 `update_and_redeploy.sh`。

安装定时任务（需要 root）：

```bash
sudo ./sing_box/Script/setup_weekly_update_timer.sh
```

特性说明：

- `OnCalendar=Mon *-*-* 03:00:00`：每周一 03:00 触发，可用 `--on-calendar` 自定义。
- `Persistent=true`：关机错过的那次会在下次开机后补跑。
- `RandomizedDelaySec=30min`：随机抖动，避开 GitHub 整点拉取高峰，可用 `--delay` 调整。
- `After=network-online.target`：联网后才执行。

常用操作：

```bash
sudo systemctl start sing-box-update.service     # 立即手动跑一次验证
journalctl -u sing-box-update.service -f         # 跟踪日志
systemctl list-timers sing-box-update.timer      # 查看下次执行时间
sudo ./sing_box/Script/setup_weekly_update_timer.sh --remove   # 卸载定时任务
```

> 注意：该流程只更新内核、UI 和规则集，不会重新生成 `config.json`（节点不变）。订阅节点变化仍需手动运行 `clash_nodes_to_singbox.py`。如果服务是用 `setup_sing_box_service.sh -n <自定义名>` 安装的，需要相应调整。

## 出站分组

脚本会根据 `--prefer` 关键词生成新加坡专用分组：

- `SG-Auto`：`urltest` 自动测速分组。
- `SG-Fallback`：同一批新加坡节点的手动选择分组。

名称包含 `实验` 的节点不会进入 `SG-Auto` 或 `SG-Fallback`，但仍保留在 `Auto` 和 `Proxy` 的完整节点列表中。`AI` 选择器默认选择 `Proxy`，也可以切换到 `SG-Auto`、`SG-Fallback`、`Auto` 或 `DIRECT`。

`Auto` 和 `Proxy` 会过滤订阅说明节点，例如 `Traffic:`、`Expire:`、`剩余流量`、`过期时间`。顶层 `outbounds` 会先保留真实节点和常用策略组，再把 `SG-Auto`、`SG-Fallback`、`Auto` 等自动/地区分组放在后面，`Fallback` 放在最后；`Proxy` 内部仍保持分组优先。

`Streaming` 是和 `AI` 类似的流媒体选择器，匹配 `streaming_domain_suffixes` 后走该组，默认选择 `Proxy`。

`Direct` 是可选的特殊直连组，仅当 `direct_domain_suffixes` 非空时生成。命中这些域名后优先走 `Direct`（默认 `DIRECT`，可在面板切换到 `Proxy`/`Auto`），优先级高于 `AI`/`Streaming`/CN 分流，适合强制某些域名走本地直连。

## EasyTier 绕过

EasyTier 的 P2P peer IP 是动态发现的，不应靠 `easytier_bypass_domains` 或手工 IP 列表长期维护。推荐做法：

- 让 EasyTier 用独立系统用户运行，例如 `easytier`。
- 添加高于 sing-box `9000+` 规则的策略路由，例如 `ip rule add pref 1000 uidrange 997-997 lookup main`。
- 在 `clash_nodes_to_singbox_config.json` 中设置 `tun_exclude_uids`，让 sing-box TUN 也显式排除 EasyTier UID。

这样可以保留 sing-box `strict_route`，同时让 EasyTier 动态 P2P 数据面稳定走物理网卡。

## 校验

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
