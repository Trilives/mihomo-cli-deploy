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

该脚本从上游发布页下载适合当前 Linux 架构的 Mihomo 核心、MetaCubeXD Web UI、`country.mmdb` 和 `geoip.metadb`，并部署到仓库根目录。

后续更新核心和 Web UI 时，可再次执行同一命令。

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

需要从局域网访问时，可将 `external-controller` 改为 `0.0.0.0:9090`，并务必设置非空 `secret`，同时按需配置防火墙。

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

服务管理命令：

```bash
sudo systemctl status mihomo --no-pager
sudo journalctl -u mihomo -f
sudo systemctl restart mihomo
sudo ./Script/setup_mihomo_service.sh --remove
```

可选参数：

```bash
# 仅设置开机自启，不立即启动
sudo ./Script/setup_mihomo_service.sh --no-start

# 使用自定义服务名
sudo ./Script/setup_mihomo_service.sh -n mihomo-main
sudo ./Script/setup_mihomo_service.sh -n mihomo-main --remove
```

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

- 更新核心和 Web UI：重新运行 `./Script/update_core_assets.sh`。
- 更新订阅：重新运行下载或转换脚本；该操作会替换 `config.yaml`。
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
