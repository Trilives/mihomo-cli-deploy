# sing-box 本地配置说明

本目录用于独立运行 sing-box，并承载由订阅转换或从根目录 `config.yaml` 提取节点后生成的 sing-box 配置。下载缓存、核心文件、Web UI 和生成配置都放在 `sing_box/` 内，避免和 Mihomo 目录互相污染。

## 目录结构

- `config.json`：转换生成的 sing-box 配置文件
- `sing-box`：sing-box 可执行文件
- `sing-box.version`：当前下载的 sing-box 版本
- `ui/`：Web UI 静态资源，供 Clash API 通过 `/ui` 访问
- `source/downloads/`：sing-box core 和 Web UI 下载缓存
- `Script/update_sing_box_core.sh`：下载并更新 sing-box core 和 Web UI
- `Script/setup_sing_box_service.sh`：注册或删除 sing-box systemd 服务
- `Script/setup_resilience.sh`：安装网络切换自愈（NetworkManager 钩子 + watchdog 定时器）
- `Script/sing_box_healthcheck.sh`：watchdog 探针，检测代理“假死”后自动重启服务
- `Script/download_sing_box_subscription.sh`：通过 subconverter 后端把订阅转换为 sing-box `config.json`
- `Script/Enhance/clash_nodes_to_singbox.py`：本地兜底转换，从根目录 Mihomo `config.yaml` 提取节点并生成 sing-box `config.json`

## 前提条件

- Linux 系统，TUN 模式和 systemd 服务通常需要 root 权限。
- `curl`、`tar`、`python3`。
- 解压 Web UI 的包如果是 zip，需要 `unzip`。
- 本地兜底转换需要 Python 包 `PyYAML`，缺失时可执行 `python3 -m pip install PyYAML`。

## 快速开始

赋予脚本执行权限：

```bash
chmod +x ./sing_box/Script/*.sh ./sing_box/Script/Enhance/*.py
```

下载 sing-box core 和 Web UI：

```bash
./sing_box/Script/update_sing_box_core.sh
```

通过 subconverter 后端转换订阅，默认输出到 `sing_box/config.json`：

```bash
./sing_box/Script/download_sing_box_subscription.sh -u 'https://your-subscribe-link'
```

如果手上已经有完整的官方转换链接（例如 `.../sub?target=clash&url=...`），可以直接传入，脚本会自动把 `target` 改成 `singbox`：

```bash
./sing_box/Script/download_sing_box_subscription.sh --converted-url 'https://your-backend/sub?target=clash&url=...'
```

如果你有自建 subconverter，建议使用自建后端：

```bash
./sing_box/Script/download_sing_box_subscription.sh -b 'http://127.0.0.1:25500' -u 'https://your-subscribe-link'
```

也可以追加 subconverter 参数：

```bash
./sing_box/Script/download_sing_box_subscription.sh -u 'https://your-subscribe-link' -p 'udp=true' -p 'emoji=true'
```

本地兜底转换当前 Mihomo 配置。该脚本读取根目录 `config.yaml` 的 `proxies`，生成一个保守的 sing-box TUN 配置：

```bash
./sing_box/Script/Enhance/clash_nodes_to_singbox.py
```

如需指定输入、输出、首选节点关键词或默认出站：

```bash
./sing_box/Script/Enhance/clash_nodes_to_singbox.py ./config.yaml ./sing_box/config.json --prefer 'Singapore,SG,新加坡,狮城' --default-outbound Proxy
```

严格模式会在遇到不支持或字段不完整的节点时直接失败：

```bash
./sing_box/Script/Enhance/clash_nodes_to_singbox.py --strict
```

检查配置：

```bash
./sing_box/sing-box check -c ./sing_box/config.json
```

如果当前 shell 设置过代理，建议同时排除本机地址：

```bash
export NO_PROXY=localhost,127.0.0.1,::1
export no_proxy=localhost,127.0.0.1,::1
```

启动 sing-box：

```bash
./sing_box/sing-box run -c ./sing_box/config.json
```

## 系统服务

注册为 systemd 服务并立即启动（会把当前 `sing_box/config.json` 复制到 `/etc/sing-box/<service>.json` 作为服务运行配置）：

```bash
sudo ./sing_box/Script/setup_sing_box_service.sh
```

仅注册开机自启，不立即启动：

```bash
sudo ./sing_box/Script/setup_sing_box_service.sh --no-start
```

查看状态：

```bash
systemctl status sing-box --no-pager
```

删除服务：

```bash
sudo ./sing_box/Script/setup_sing_box_service.sh --remove
```

如需自定义服务名：

```bash
sudo ./sing_box/Script/setup_sing_box_service.sh -n sing-box-main
sudo ./sing_box/Script/setup_sing_box_service.sh -n sing-box-main --remove
```

## 网络切换自愈

sing-box 用 `auto_detect_interface` 把出站绑定到上行网卡。当网卡在开机时晚于服务启动、中途掉线、或在不同网络间漫游（笔记本 / 手机热点 / 机场 WiFi 常见）时，sing-box 会卡在 `network: missing default interface`，此后所有连接（含 DNS）全部超时——但进程并不退出，`Restart=on-failure` 不会触发，代理“假死”直到被重启。`journalctl -u sing-box` 中反复出现的 `missing default interface`、`network is unreachable` 即此症状。

`setup_resilience.sh` 安装两套互补的自愈机制：

- **A. NetworkManager 钩子**：真实网卡 `up` 或连通性变化时自动重启 sing-box，让它重新探测网卡。解决“开机太早”和“切换网络”，从源头修复。安装到 `/etc/NetworkManager/dispatcher.d/90-<service>-restart`，会忽略 sing-box 自己的 tun 设备并对事件做防抖，避免重启风暴。
- **B. systemd watchdog 定时器**：默认每 2 分钟通过混合代理（`127.0.0.1:7890`）探测一次，发现“有上行但代理打不通”才重启；没有上行时不动作，避免空转。兜底那些不触发 NetworkManager 事件的静默掉线。

安装（幂等，可重复执行）：

```bash
sudo ./sing_box/Script/setup_resilience.sh
```

可调探测间隔或服务名：

```bash
sudo ./sing_box/Script/setup_resilience.sh --interval 90s
sudo ./sing_box/Script/setup_resilience.sh -n sing-box-main
```

手动探测一次、查看日志、删除：

```bash
sudo systemctl start sing-box-watchdog.service
journalctl -u sing-box-watchdog.service -f
sudo ./sing_box/Script/setup_resilience.sh --remove
```

## Web UI

本地兜底转换脚本会自动写入 `experimental.clash_api`。**默认推荐仅本地访问**：面板监听回环地址 `127.0.0.1:9090`，不开放到局域网。

```json
{
  "experimental": {
    "clash_api": {
      "external_controller": "127.0.0.1:9090",
      "external_ui": "ui",
      "default_mode": "rule"
    }
  }
}
```

启动后在本机访问 `http://127.0.0.1:9090/ui`。需要在另一台机器上查看时，建议用 SSH 端口转发，而不是开放到局域网：

```bash
ssh -N -L 9090:127.0.0.1:9090 user@server   # 在本地机器执行，再访问 http://127.0.0.1:9090/ui
```

不想敲命令也可以用图形化的 SSH 端口转发工具：[Trilives/Port_transfer_ssh_ui](https://github.com/Trilives/Port_transfer_ssh_ui)。

确有需要开放到局域网时，可在 `clash_nodes_to_singbox_config.json` 中设置 `"lan_panel": true`（或转换时加 `--lan-panel`），脚本会把面板改为监听 `0.0.0.0:9090` 并放行私有网络访问。开放后请务必设置 `secret`，避免同网段设备直接控制代理，并按需配置防火墙。

安装服务时也可控制面板暴露：`setup_sing_box_service.sh` 会按仓库根目录 `.env` 中的 `ALLOW_LAN`（默认 `false`，参考 `.env.example`）重写暂存配置的 `external_controller`——`false` 强制回 `127.0.0.1:9090`，`true` 改为 `0.0.0.0:9090` 并放行私有网络访问（原有端口保留）。也可临时用环境变量：`ALLOW_LAN=true sudo ./sing_box/Script/setup_sing_box_service.sh`。注意 sing-box 的代理 inbound 始终监听回环，此开关只影响面板。

## 注意事项

- 默认推荐使用 `Script/download_sing_box_subscription.sh` 走 subconverter 后端生成 sing-box 配置。
- `https://sub-web.wcc.best` 和 `https://sublink.dev` 是前端页面，不一定能直接作为脚本 API 后端；脚本需要真实的 subconverter 后端，例如自建 `http://127.0.0.1:25500`。
- 本地 Python 转换脚本只是兜底方案，当前支持从 `proxies` 转换 `anytls`、`trojan`、`ss`/`shadowsocks`、`vmess`、`vless`、`hysteria2`/`hy2`、`tuic`、`socks`/`socks5`、`http` 节点。
- 本地兜底转换会生成 `tun` 和 `mixed` 入站、`Proxy`/`Auto`/`AI`/`Streaming`/`SG-Auto`/`SG-Fallback`/`Fallback` 出站、基础 DNS、基础分流规则和 Clash API。完整 CN 分流规则集尚未内置。
- `Auto` 和 `Proxy` 会过滤订阅说明节点，例如 `Traffic:`、`Expire:`、`剩余流量`、`过期时间`。
- 顶层 `outbounds` 会先保留真实节点和常用策略组，再把 `SG-Auto`、`SG-Fallback`、`Auto` 等自动/地区分组放在后面，`Fallback` 放在最后；`Proxy` 内部仍保持分组优先，便于常规切换。
- `SG-Auto` 和 `SG-Fallback` 只从首选新加坡节点中生成，并排除名称包含 `实验` 的节点；`AI` 和 `Streaming` 选择器默认优先选择 `Proxy`，也可手动切到 `SG-Auto`、`SG-Fallback`、`Auto` 或 `DIRECT`。
- 本地兜底转换会从 TUN 自动路由中排除 `127.0.0.0/8`、`0.0.0.0/8`、`::1/128`，并强制 `localhost` 和这些本机地址走 `DIRECT`。
- EasyTier 不再依赖域名/IP 列表绕过 sing-box。推荐让 EasyTier 使用独立系统用户运行，并在系统路由中添加优先级高于 sing-box 的 `uidrange <uid>-<uid> lookup main` 规则；生成脚本可通过 `tun_exclude_uids` 同步写入 sing-box TUN 的 `exclude_uid`。
- 本地兜底转换仍会让 `tailscale`、`tailscaled` 等配置中的 `bypass_process_names` 进程直连。
- shell 中建议同时设置本机地址不走代理：`export NO_PROXY=localhost,127.0.0.1,::1` 和 `export no_proxy=localhost,127.0.0.1,::1`。
- Shadowsocks `obfs` 插件节点会转换为 `obfs-local` 插件配置，运行环境需要安装 `obfs-local`，否则该类节点运行时会失败。
- systemd 脚本安装服务时会把当前配置复制到 `/etc/sing-box/<service>.json`，后续修改 `sing_box/config.json` 后需要重新执行安装脚本或手动同步服务配置。
- 生成的 `sing_box/config.json` 包含节点信息，已在根目录 `.gitignore` 中忽略。
- `sing_box/ui/`、`sing_box/sing-box`、`sing_box/source/downloads/` 都是生成产物，已忽略。
