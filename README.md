# Mihomo / sing-box Linux CLI 部署脚本

用于在 Linux 上从零部署 Mihomo 或 sing-box 的脚本集合。仓库本身只提供安装、更新和配置辅助脚本；核心程序、Web UI、规则数据库以及包含节点信息的配置文件，会在本地运行脚本后生成。

## 功能

- 下载并更新 Mihomo 核心、MetaCubeXD Web UI 与地理数据库。
- 直接下载 Clash/Mihomo 订阅，或通过 subconverter 后端转换订阅。
- 将 Mihomo 作为 systemd 服务运行。
- 为 Mihomo 配置追加香港、新加坡的 `fallback` / `url-test` 分组。
- 提供独立的 [sing-box 部署流程](sing_box/README.md)，支持订阅转换、本地节点转换和 systemd 服务。

## 首次使用前

### 环境要求

- Linux 系统。
- `bash`、`curl`、`tar`、`gzip`、`find`、`install`。
- 下载到 `.zip` 格式的 Web UI 时需要 `unzip`。
- 启用 TUN 或安装 systemd 服务时需要 root 权限。

### 克隆仓库

```bash
git clone https://github.com/Trilives/mihomo-cli-deploy.git
cd mihomo-cli-deploy
chmod +x ./Script/*.sh
```

首次克隆完成后，仓库不包含核心、订阅配置或 Web UI 等运行产物。以下文件均由后续步骤在本地创建，并已通过 `.gitignore` 排除：

```text
config.yaml        # Mihomo 配置，通常包含订阅节点
mihomo             # Mihomo 核心程序
ui/                # MetaCubeXD Web UI
country.mmdb       # 地理数据库
geoip.metadb       # 地理数据库
source/downloads/  # 下载缓存
```

## 部署 Mihomo

### 1. 下载核心与 Web UI

```bash
./Script/update_core_assets.sh
```

该脚本从上游发布页下载适合当前 Linux 架构的 Mihomo 核心、MetaCubeXD Web UI、`country.mmdb` 和 `geoip.metadb`，并部署到仓库根目录，同时把版本号写入 `mihomo.version`。

后续更新核心和 Web UI 时，可再次执行同一命令。

老 CPU 缺少现代指令集时，可改用 compatible 构建：

```bash
./Script/update_core_assets.sh --variant compatible
```

**GitHub 限流（可选但推荐）**：脚本通过 GitHub API 查询最新版本，匿名访问限流为 60 次/小时，容易触发 `403`。可在仓库根目录的 `.env` 中放置一个 token（参考 `.env.example`），脚本会自动读取并鉴权（限流提升到 5000 次/小时）：

```bash
cp .env.example .env
# 编辑 .env，填入 GITHUB_TOKEN=github_pat_xxx（只需公共读取权限）
```

`.env` 已被 `.gitignore` 忽略，不会提交；也可改用环境变量 `GITHUB_TOKEN`/`GH_TOKEN`。

**下载代理（可选）**：如果本机直连 GitHub 不稳定，可以让局域网内另一台网络通畅的设备共享代理（开放 `allow-lan`），把它的「主机+端口」填到 `.env` 的 `DOWNLOAD_PROXY`，更新脚本会优先走该代理下载，失败再自动回退直连：

```bash
# 编辑 .env，填入局域网代理设备的地址和端口
DOWNLOAD_PROXY=http://192.168.2.7:7897     # 也支持 socks5h://192.168.2.7:7897
```

也可改用环境变量 `DOWNLOAD_PROXY`；临时强制直连可设 `SING_BOX_NO_PROXY=1`。

### 2. 生成 `config.yaml`

选择符合订阅格式的一种方式。

#### 方式 A：订阅已经是 Clash/Mihomo 配置

```bash
./Script/download_subscription.sh -u 'https://your-subscription-url'
```

#### 方式 B：将原始订阅转换为 Clash/Mihomo 配置

```bash
./Script/gen_convert_url.sh -u 'https://your-subscription-url'
```

使用镜像后端或自建 subconverter：

```bash
./Script/gen_convert_url.sh -b mirror -u 'https://your-subscription-url' -p 'emoji=true'
./Script/gen_convert_url.sh -b 'http://127.0.0.1:25500' -u 'https://your-subscription-url'
```

脚本默认将结果保存为根目录的 `config.yaml`。重新下载或转换订阅会覆盖该文件，请在覆盖前备份自行添加的配置。

### 3. 启用 Web UI

如订阅生成的配置未包含控制面板设置，可将以下字段合并到 `config.yaml`：

```yaml
external-controller: 127.0.0.1:9090
external-ui: ui
secret: "change-this-secret"
mode: Rule
```

启动后，本机访问地址为：

```text
http://127.0.0.1:9090/ui/
```

**默认推荐仅本地访问**：保持 `external-controller: 127.0.0.1:9090`，面板只监听回环地址、不开放到局域网。需要在另一台机器上查看时，建议用 SSH 端口转发，把远端面板映射到本地后再用浏览器打开 `http://127.0.0.1:9090/ui/`：

```bash
ssh -N -L 9090:127.0.0.1:9090 user@server   # 在本地机器执行
```

不想敲命令也可以用图形化的 SSH 端口转发工具：[Trilives/Port_transfer_ssh_ui](https://github.com/Trilives/Port_transfer_ssh_ui)。

仅在确有需要时才将 `external-controller` 改为 `0.0.0.0:9090` 开放到局域网，并务必设置非空 `secret`、按需配置防火墙限制可访问范围。

### 4. 可选：启用 TUN

如需让系统流量自动经过 Mihomo，可按实际网络环境在 `config.yaml` 中添加 TUN 配置：

```yaml
tun:
  enable: true
  stack: gvisor
  auto-route: true
  auto-detect-interface: true
  dns-hijack:
    - any:53
    - tcp://any:53
```

TUN 通常需要 root 权限。DNS 监听方式、TUN stack 与 MTU 取值可能因发行版、内核和已有网络服务而异；如启动后出现断网或 DNS 冲突，先停用服务恢复网络，再调整配置。

### 5. 测试运行

不启用 TUN 时，可以先以前台方式检查配置能否启动：

```bash
./mihomo -d .
```

启用了 TUN 时，以 root 运行测试：

```bash
sudo ./mihomo -d .
```

启动成功后，打开 Web UI 检查节点与代理分组是否已经加载。按 `Ctrl+C` 停止前台程序。

### 6. 安装为 systemd 服务

确认 `mihomo` 和 `config.yaml` 已生成后，执行：

```bash
sudo ./Script/setup_mihomo_service.sh
```

安装脚本会在发现 dashboard 未完整配置时，自动补齐 `external-controller`、`external-ui`，并在缺少面板密码时生成一个随机 `secret`，以便 Web UI 能正常进入节点选择；它不会替你改动现有订阅节点或手工编写的代理分组，已设置的 `external-controller` 监听地址也会保留。

`allow-lan` 默认写为 `false`（代理端口仅本机可用，面板始终绑定本地地址）。如需让局域网内其他设备把本机当代理使用，在根目录 `.env` 中设置 `ALLOW_LAN=true`（参考 `.env.example`），或临时用环境变量 `ALLOW_LAN=true sudo ./Script/setup_mihomo_service.sh`。注意这只影响代理端口是否对局域网开放，与面板是否暴露无关——面板暴露由 `external-controller` 的监听地址决定（见第 3 节）。

**自包含运行时目录**：脚本会把运行所需文件（二进制、`<服务名>.yaml`、`country.mmdb`、`geoip.metadb`、`ui/`）暂存到 `/etc/mihomo`，服务以 `mihomo -d /etc/mihomo -f /etc/mihomo/<服务名>.yaml` 运行。这样服务与仓库路径、运行用户解耦，避免源码位于 `/home` 时的目录遍历权限问题。安装前会用 `mihomo -t` 校验暂存配置。

服务管理命令：

```bash
sudo systemctl status mihomo --no-pager
sudo journalctl -u mihomo -f
sudo systemctl restart mihomo
sudo ./Script/setup_mihomo_service.sh --remove
```

`--remove` 会停止并删除服务，同时清理该服务在 `/etc/mihomo` 下的暂存配置；当目录中已无其它受管服务时，连同共享文件（二进制、geo、ui）一并删除。

可选参数：

```bash
# 仅设置开机自启，不立即启动
sudo ./Script/setup_mihomo_service.sh --no-start

# 使用自定义服务名（暂存为 /etc/mihomo/<名>.yaml，可多服务共存）
sudo ./Script/setup_mihomo_service.sh -n mihomo-main
sudo ./Script/setup_mihomo_service.sh -n mihomo-main --remove

# 自定义运行时目录
sudo ./Script/setup_mihomo_service.sh -d /opt/mihomo
```

### 7. 每周自动更新（可选）

`update_and_redeploy.sh` 会依次执行 `update_core_assets.sh`（更新核心、Web UI、geo 数据）和 `setup_mihomo_service.sh`（重新暂存并重启服务）。`setup_weekly_update_timer.sh` 则安装一个 systemd timer，默认每周一 03:00 自动跑前者。

```bash
sudo ./Script/setup_weekly_update_timer.sh
```

特性：每周一 03:00 触发（`--on-calendar` 可改）、`Persistent=true`（关机错过的会开机补跑）、`RandomizedDelaySec=30min`（错峰、避免 GitHub 限流，`--delay` 可调）。

```bash
sudo systemctl start mihomo-update.service        # 立即手动跑一次
journalctl -u mihomo-update.service -f            # 跟踪日志
systemctl list-timers mihomo-update.timer         # 查看下次执行时间
sudo ./Script/setup_weekly_update_timer.sh --remove   # 卸载定时任务
```

> 提示：该流程只更新核心/UI/geo，不会重新下载订阅（节点不变）；订阅更新仍需手动跑下载或转换脚本。mihomo 与 sing-box 服务互斥，请只安装与当前运行栈对应的 timer。

## 可选：追加地区测速或故障切换分组

`Script/Enhance/` 中的 Python 脚本读取已有 `config.yaml`，从 `proxies` 中匹配香港或新加坡节点，并将新分组加入首个选择器。使用前应先备份配置：

```bash
cp config.yaml config.yaml.bak.local

python3 ./Script/Enhance/add_hk_url_test.py
python3 ./Script/Enhance/add_hk_fallback.py
python3 ./Script/Enhance/add_sg_url_test.py
python3 ./Script/Enhance/add_sg_fallback.py
```

脚本要求订阅配置中存在标准的 `proxies:` 和 `proxy-groups:` 段，且节点名称中包含对应地区关键词。没有匹配节点时脚本会报错退出。

## 部署 sing-box

如希望运行 sing-box 而不是 Mihomo，请按 [sing_box/README.md](sing_box/README.md) 操作。该流程会在 `sing_box/` 下独立生成核心程序、Web UI 与 `config.json`，不会与 Mihomo 的运行文件混用。

## 更新与安全注意事项

- 更新核心和 Web UI：重新运行 `./Script/update_core_assets.sh`，或安装每周定时器自动更新（见上文「每周自动更新」）。
- 更新订阅：重新运行下载或转换脚本；该操作会替换 `config.yaml`。
- `.env` 用于存放 `GITHUB_TOKEN` 等本地密钥，已被 `.gitignore` 忽略，切勿提交；token 一旦泄露应立即在 GitHub 重置。
- `config.yaml` 和 `sing_box/config.json` 通常包含节点凭证，不要提交到公开仓库，也不要在问题报告中直接粘贴。
- 订阅链接本身可能包含 token；终端历史、截图和日志分享前应检查并打码。
- 对外开放 Web UI 时请配置访问密码，并限制管理端口的可访问范围。

## 常见排查

### 服务启动失败

```bash
sudo systemctl status mihomo --no-pager
sudo journalctl -u mihomo -n 100 --no-pager
```

确认根目录存在可执行的 `mihomo` 与有效的 `config.yaml`。启用 TUN 时，确认服务以具备所需权限的用户运行。

### Web UI 无法打开

确认以下项目：

```bash
test -d ui && echo 'ui exists'
grep -E '^(external-controller|external-ui|secret):' config.yaml
```

`external-ui` 应指向 `ui`，访问地址应与 `external-controller` 的监听地址和端口一致。

### 启用 TUN 后网络异常

先停止 Mihomo 以恢复网络，再检查日志以及本机已有的 DNS、VPN、TUN 或虚拟组网服务是否发生冲突：

```bash
sudo systemctl stop mihomo
sudo journalctl -u mihomo -n 100 --no-pager
ip route show
```

必要时先禁用 TUN 验证普通代理是否可用，再逐项恢复 TUN 与 DNS 设置。
