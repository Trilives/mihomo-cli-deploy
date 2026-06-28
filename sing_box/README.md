# sing-box 本地部署

在 Linux 上独立运行 sing-box。核心程序、Web UI、下载缓存和生成的配置都放在 `sing_box/` 内，与根目录的 Mihomo 运行文件互不干扰。

`config.json`（含节点信息）、`sing-box` 可执行文件、`ui/`、`source/downloads/` 都是本地生成的产物，已在 `.gitignore` 中忽略。

## 前提条件

- Linux 系统；TUN 模式和 systemd 服务通常需要 root。
- `curl`、`tar`、`python3`（Web UI 为 zip 时还需 `unzip`）。
- 本地兜底转换需要 `PyYAML`：`python3 -m pip install PyYAML`。

## 快速开始

```bash
# 0. 赋予执行权限
chmod +x ./sing_box/Script/*.sh ./sing_box/Script/Enhance/*.py

# 1. 下载 sing-box 核心、Web UI 和 CN 规则集
./sing_box/Script/update_sing_box_core.sh

# 2. 生成 sing_box/config.json（二选一，见下）

# 3. 校验配置
./sing_box/sing-box check -c ./sing_box/config.json

# 4. 前台试运行（Ctrl+C 退出）
./sing_box/sing-box run -c ./sing_box/config.json
```

> 当前 shell 设过代理时，建议排除本机地址：
> `export NO_PROXY=localhost,127.0.0.1,::1 no_proxy=localhost,127.0.0.1,::1`

### 第 2 步生成配置 · 方式 A：subconverter 后端（推荐）

通过 subconverter 后端把订阅转成 sing-box 配置，默认输出到 `sing_box/config.json`：

```bash
./sing_box/Script/download_sing_box_subscription.sh -u 'https://your-subscribe-link'
```

- 已有完整官方转换链接：`--converted-url '.../sub?target=clash&url=...'`（脚本自动把 `target` 改为 `singbox`）。
- 自建后端：加 `-b 'http://127.0.0.1:25500'`。
- 追加 subconverter 参数：`-p 'udp=true' -p 'emoji=true'`。

> `sub-web.wcc.best`、`sublink.dev` 是前端页面，未必能作脚本 API 后端；脚本需要真实的 subconverter 后端。

### 第 2 步生成配置 · 方式 B：本地兜底转换

从根目录 Mihomo `config.yaml` 的 `proxies` 提取节点，生成保守的 sing-box TUN 配置。完整说明见 [Script/Enhance/README.md](Script/Enhance/README.md)。

```bash
./sing_box/Script/Enhance/clash_nodes_to_singbox.py
```

## 系统服务

注册为 systemd 服务并启动（会把当前 `config.json` 复制到 `/etc/sing-box/<服务名>.json` 作为运行配置）：

```bash
sudo ./sing_box/Script/setup_sing_box_service.sh              # 注册并启动
sudo ./sing_box/Script/setup_sing_box_service.sh --no-start   # 仅开机自启
sudo ./sing_box/Script/setup_sing_box_service.sh --remove     # 删除服务
sudo ./sing_box/Script/setup_sing_box_service.sh -n sing-box-main   # 自定义服务名
systemctl status sing-box --no-pager                         # 查看状态
```

> 安装后再改 `sing_box/config.json`，需重新执行安装脚本以同步到 `/etc/sing-box/`。

## 交互式切换 / 固定节点

`Script/Enhance/select_singbox_node.py` 是一个三步式终端脚本，本质是把选中项设为代理分组（默认 `Proxy`）的**第一个成员**并对齐 `default`。sing-box selector 在无持久化选择时取第一个成员，固定它后，重启、网络自愈等流程重启 sing-box 时就不会被 `SG-Auto` 这类 `urltest` 自动测速组乱切节点。

```bash
./sing_box/Script/Enhance/select_singbox_node.py                    # 默认读 sing_box/config.json
./sing_box/Script/Enhance/select_singbox_node.py path/to/config.json
```

服务在跑时还会通过 Clash API 实时切换。完整流程、环境变量（`SINGBOX_GROUP` / `RESTART_ARGS`）见 [Script/Enhance/README.md](Script/Enhance/README.md#交互式切换--固定节点)。

> 重新跑 `clash_nodes_to_singbox.py` 会重置成员顺序，需要时再跑一次本脚本即可。

## 网络切换自愈

sing-box 用 `auto_detect_interface` 绑定上行网卡。网卡晚于服务启动、中途掉线、或在不同网络间漫游（笔记本 / 手机热点 / 机场 WiFi）时，sing-box 会卡在 `network: missing default interface`，所有连接（含 DNS）超时——但进程不退出，`Restart=on-failure` 不触发，代理“假死”直到被重启（`journalctl -u sing-box` 反复出现 `missing default interface`、`network is unreachable`）。

`setup_resilience.sh` 安装两套互补机制：

- **NetworkManager 钩子**：真实网卡 `up` 或连通性变化时重启 sing-box，让它重新探测网卡。从源头修复“开机太早”和“切换网络”；忽略 sing-box 自身 tun 设备并对事件防抖，避免重启风暴。
- **systemd watchdog 定时器**：默认每 2 分钟经混合代理（`127.0.0.1:7890`）探测，仅当“有上行但代理打不通”才重启；无上行时不动作。兜底不触发 NetworkManager 事件的静默掉线。

```bash
sudo ./sing_box/Script/setup_resilience.sh                  # 安装（幂等）
sudo ./sing_box/Script/setup_resilience.sh --interval 90s   # 调探测间隔
sudo ./sing_box/Script/setup_resilience.sh -n sing-box-main # 指定服务名
sudo systemctl start sing-box-watchdog.service              # 手动探测一次
sudo ./sing_box/Script/setup_resilience.sh --remove         # 删除
```

## Web UI

转换脚本会写入 `experimental.clash_api`，**默认仅本地访问**：面板监听 `127.0.0.1:9090`，启动后在本机打开 `http://127.0.0.1:9090/ui`。

需要在另一台机器查看时，用 SSH 端口转发而非开放到局域网：

```bash
ssh -N -L 9090:127.0.0.1:9090 user@server   # 本地执行，再访问 http://127.0.0.1:9090/ui
```

不想敲命令可用图形化工具 [Trilives/Port_transfer_ssh_ui](https://github.com/Trilives/Port_transfer_ssh_ui)。

确需开放到局域网时，在 `Script/Enhance/clash_nodes_to_singbox_config.json` 设 `"lan_panel": true`（或转换时加 `--lan-panel`），面板改为监听 `0.0.0.0:9090` 并放行私有网络；务必设置 `secret` 并配置防火墙。安装服务时也可由根目录 `.env` 的 `ALLOW_LAN`（默认 `false`，见 `.env.example`）控制面板暴露，或临时 `ALLOW_LAN=true sudo ./sing_box/Script/setup_sing_box_service.sh`。代理 inbound 始终只监听回环，此开关只影响面板。

## 定期更新

本仓库用本地 `rule_set`（启动时一次性读入），需定期更新 `.srs` 并重启服务。`update_and_redeploy.sh` 依次跑核心/UI/规则集更新与服务重装；`setup_weekly_update_timer.sh` 安装每周定时任务。详见 [Script/Enhance/README.md](Script/Enhance/README.md#每周自动更新)。

## 目录结构

| 路径 | 说明 |
| --- | --- |
| `config.json` | 生成的 sing-box 配置（已忽略） |
| `sing-box` / `sing-box.version` | 核心程序与版本号（已忽略） |
| `ui/` | Web UI 静态资源，经 Clash API `/ui` 访问（已忽略） |
| `source/downloads/` | 核心与 UI 下载缓存（已忽略） |
| `ruleset/` | CN 分流规则集 `geosite-cn.srs` / `geoip-cn.srs` |
| `Script/update_sing_box_core.sh` | 下载 / 更新核心、Web UI、规则集 |
| `Script/setup_sing_box_service.sh` | 注册 / 删除 systemd 服务 |
| `Script/setup_resilience.sh` | 安装网络切换自愈 |
| `Script/sing_box_healthcheck.sh` | watchdog 探针 |
| `Script/setup_weekly_update_timer.sh` | 安装每周更新定时器 |
| `Script/update_and_redeploy.sh` | 更新核心/UI/规则集并重启服务 |
| `Script/download_sing_box_subscription.sh` | 经 subconverter 把订阅转为 `config.json` |
| `Script/Enhance/clash_nodes_to_singbox.py` | 本地兜底：从 Mihomo `config.yaml` 生成 `config.json` |
| `Script/Enhance/select_singbox_node.py` | 交互式切换 / 固定节点 |

## 安全注意事项

- `config.json` 含节点凭证，不要提交或在问题报告中粘贴。
- 对外开放 Web UI 时务必设 `secret` 并限制管理端口可访问范围。
- 本地兜底转换是兜底方案；优先用 subconverter 后端。转换细节、DNS bootstrap、EasyTier 绕过等见 [Script/Enhance/README.md](Script/Enhance/README.md)。
