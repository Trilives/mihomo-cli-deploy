# Mihomo 本地配置说明

本目录用于运行 Mihomo（含 Web UI）并管理由订阅下载或订阅转换生成的配置。

## 目录结构(均由脚本下载，初始仓库没有)

- `config.yaml`：主配置文件（核心）
- `mihomo`：Mihomo 可执行文件
- `ui/`：Web UI 静态资源（`external-ui: ui`）
- `source/`：订阅/规则来源相关文件
- `country.mmdb`、`geoip.metadb`、`geoip.dat`、`GeoSite.dat`：地理库和规则数据库

---

## 🚀 快速开始（从零开始）

> **前提条件**：首次使用前，需要赋予脚本执行权限：
> ```bash
> chmod +x ./Script/*.sh
> ```

### 第一步：下载核心文件

运行官方资源更新脚本，下载最新的 Mihomo、Web UI 和地理数据库：

```bash
./Script/update_core_assets.sh
```

该脚本会自动：
- 下载 `mihomo` 可执行文件
- 下载 `country.mmdb` 和 `geoip.metadb` 数据库
- 下载并解压 Web UI 到 `ui/` 目录

### 第二步：准备配置文件

有两种方式获得 `config.yaml`：

**方式 A：原样下载订阅（适用于订阅本身已经是 Clash/Mihomo 格式）**

直接运行脚本，把订阅内容原样下载到本地：

```bash
./Script/download_subscription.sh -u 'https://your-subscribe-link'
```

脚本会把订阅内容保存到 `config.yaml`。

如需自定义文件名：
```bash
./Script/download_subscription.sh -u 'https://your-subscribe-link' -f 'config.yaml'
```

**方式 B：使用订阅转换（适用于需要先把原始订阅转成 clash 格式）**

```bash
./Script/gen_convert_url.sh -u 'https://your-subscribe-link'
```

脚本会输出转换链接和保存路径，配置文件自动保存到 `config.yaml`。

如需自定义参数或文件名：
```bash
./Script/gen_convert_url.sh -u 'https://your-subscribe-link' -b mirror -p 'emoji=true' -f 'config.yaml'
```

**方式 C：手动编写配置**

参考 Mihomo 官方文档，手动创建 `config.yaml`。

### 第三步：配置关键项

编辑 `config.yaml`，确保包含以下内容（合并到文件顶部）：

```yaml
# 控制面板
external-controller: 0.0.0.0:9090
external-ui: ui
secret: ""  # 可选：设置访问密码

# 代理模式
mode: Rule

# TUN 配置（推荐启用，Ubuntu 优化版）
tun:
  enable: true
  stack: gvisor             # Ubuntu 必须用 gvisor（mixed/system 无法转发 TCP）
  auto-route: true
  auto-detect-interface: true
  mtu: 1500                 # 标准 MTU，兼容性最好
  dns-hijack:
    - any:53
    - tcp://any:53

# DNS 配置（普通解析，当前更推荐）
dns:
  enable: true
  ipv6: false
  listen: 0.0.0.0:53        # 若 53 被 systemd-resolved 占用，改为 0.0.0.0:1053

  # 兼容性过滤列表：保留给订阅或特殊服务使用，不启用 fake-ip 时通常不会生效
  fake-ip-filter:
    - "*.lan"
    - "*.srv.nintendo.net"
    - "*.stun.playstation.net"
    - xbox.*.microsoft.com
    - "*.xboxlive.com"
    - "*.teafone.com"
    - "*.sktswe.net"
    - rtc.goodfone.co.kr
    - "*.chattti.com"

  # 主 DNS：优先使用国内低延迟解析，DoT 作为加密备用
  nameserver:
    - 119.29.29.29
    - 223.5.5.5
    - tls://223.5.5.5:853
    - tls://223.6.6.6:853
    - tls://120.53.53.53
    - tls://1.12.12.12
```

> **⚠️ Ubuntu 用户重要提示**：
> - DNS 监听端口优先按当前系统选择：若 `53` 未被占用，可用 `0.0.0.0:53`；若与 `systemd-resolved` 冲突，则改为 `0.0.0.0:1053`
> - TUN stack **必须**使用 `gvisor`（`mixed` 和 `system` 存在 TCP 转发缺陷，会导致网络完全不可用）
> - MTU 使用标准值 `1500`（更高的值可能导致兼容性问题）
> - 当前不建议主动启用 `enhanced-mode: fake-ip`；普通解析在本环境下更快，也更少影响系统更新、内网和部分直连服务

如普通解析遇到严重污染、分流异常或特定应用必须依赖 fake-ip 行为，可以把 DNS 段切换为下面的备选方案：

```yaml
# DNS 配置（fake-ip 备选方案）
dns:
  enable: true
  ipv6: false
  enhanced-mode: fake-ip
  listen: 0.0.0.0:1053      # 若 53 被占用，使用 1053 避免与 systemd-resolved 冲突
  fake-ip-range: 198.18.0.1/16

  fake-ip-filter:
    - '*.lan'
    - '*.local'
    - '+.ubuntu.com'
    - '+.debian.org'
    - 'pool.ntp.org'
    - '+.ntp.org'

  default-nameserver:
    - 223.5.5.5
    - 119.29.29.29
    - 114.114.114.114

  nameserver:
    - https://dns.alidns.com/dns-query
    - https://doh.pub/dns-query
    - 223.5.5.5

  fallback:
    - https://1.1.1.1/dns-query
    - https://dns.google/dns-query
    - tls://8.8.8.8:853

  fallback-filter:
    geoip: true
    geoip-code: CN
```

### 第四步：测试启动

在当前目录启动 Mihomo（不需要 root 权限）：

```bash
./mihomo -d .
```

验证日志输出是否正常，例如应该看到：
```
INFO[XX:XX:XX] Mihomo started
INFO[XX:XX:XX] RESTful API listening at 0.0.0.0:9090
INFO[XX:XX:XX] External UI: ui
```

### 第五步：验证功能

打开浏览器访问控制面板和 Web UI：

**访问方式：**
```
# Web UI（推荐）
http://localhost:9090/ui/

# 或直接访问API
http://localhost:9090
```

**UI 访问说明：**
- 若配置了 `external-ui: ui`，则自动在 `/ui/` 路径下提供 Web 界面
- UI 文件位于本地 `ui/` 目录中
- 首次打开可能需要稍等，让 Mihomo 加载完成

**局域网访问：**

如果在 `config.yaml` 中配置了 `external-controller: 0.0.0.0:9090`，则该设备的局域网内其他主机也可以访问：

```
# 从其他设备访问此设备的 Web UI
http://<your-machine-ip>:9090/ui/

# 示例（假设此设备 IP 为 192.168.1.100）
http://192.168.1.100:9090/ui/
```

> **安全提示**：若不需要局域网访问，可将 `external-controller` 改为 `127.0.0.1:9090`（仅本机访问）

**检查项：**
- ✓ Web UI 能否正常打开
- ✓ 是否显示代理节点
- ✓ 规则数量是否正确
- ✓ 代理分组是否正常

**功能测试（可选）：**

在 Web UI 中选择一个代理，然后尝试访问外部网址测试连接：

```bash
# 终端测试（配置了 TUN 自动接管）
curl -I https://www.google.com

# 或使用代理模式指定代理访问
# 在 Web UI 中切换到目标代理分组，然后访问
```

在 Web UI 中也可以看到实时的流量统计和连接状态。若能成功访问外部网站，说明代理正常工作。

按 `Ctrl+C` 停止 Mihomo。

### 第六步：安装为系统服务（可选）

如果需要 Mihomo 开机自启，安装为 systemd 服务：

```bash
# 一键安装并启动
sudo ./Script/setup_mihomo_service.sh

# 查看服务状态
sudo systemctl status mihomo

# 查看实时日志
sudo journalctl -u mihomo -f
```

> **注意**：如果启用了 TUN 模式，需要 root 权限才能正常接管网络流量，建议使用 systemd 服务以 root 身份运行。

> **虚拟内网配置提示**（Tailscale 等）：如在配置 Tailscale 等虚拟内网时，应先关闭 Mihomo 服务，待 Tailscale 登录完成并获得内网 IP 后，再启动 Mihomo 服务。这样可以避免 TUN 模式与虚拟内网的冲突：
> ```bash
> # 关闭 Mihomo 服务
> sudo systemctl stop mihomo
>
> # 登录 Tailscale 并获得内网 IP
> sudo tailscale up
>
> # 登录完成后重启 Mihomo
> sudo systemctl start mihomo
> ```

---

## 📜 脚本详解

### 官方资源一键更新脚本

`Script/update_core_assets.sh` 会从官方仓库自动下载并部署以下内容：

- `country.mmdb`、`geoip.metadb`：来自 `MetaCubeX/meta-rules-dat`
- `mihomo`：来自 `MetaCubeX/mihomo` 最新发布
- `ui`：来自 `MetaCubeX/metacubexd` 最新发布

脚本行为：

- 所有下载文件先保存到 `source/downloads/`
- 自动解压并移动到根目录对应位置：
  - `country.mmdb`
  - `geoip.metadb`
  - `mihomo`
  - `ui/`

使用方式：

```bash
./Script/update_core_assets.sh
```

建议更新后检查：

```bash
./mihomo -v
ls -lah ui | head
```

### 订阅原样下载脚本

`Script/download_subscription.sh` 用于把已经是 Clash/Mihomo 格式的订阅内容直接下载到本地。

参数说明：
- `-u, --url <url>`：订阅链接（必填）
- `-f, --filename <name>`：保存文件名（默认：config.yaml）

使用示例：

```bash
# 直接下载订阅到 config.yaml
./Script/download_subscription.sh -u 'https://example.com/sub?token=abc'

# 保存为自定义文件名
./Script/download_subscription.sh -u 'https://example.com/sub?token=abc' -f 'my-config.yaml'
```

### 订阅转换链接生成脚本

`Script/gen_convert_url.sh` 自动生成转换链接并直接下载保存配置文件。

支持功能：

- 官方后端：`https://sub.fndroid.com`
- 镜像（肥羊）后端：`https://api.v1.mk`
- 自定义后端地址
- 附加任意参数（如 `emoji=true`、`udp=true` 等）
- 自定义文件名和远程配置模板

参数说明：
- `-u, --url <url>`：原始订阅链接（必填）
- `-b, --backend <name|url>`：后端选择，可选 `official` | `mirror` | 自定义 URL（默认：official）
- `-t, --target <target>`：转换目标格式（默认：clash）
- `-c, --config <url>`：远程配置模板 URL（可选）
- `-f, --filename <name>`：保存文件名（默认：config.yaml）
- `-p, --param <k=v>`：追加自定义参数（可重复）

使用示例：

```bash
# 使用官方后端，保存为 config.yaml（最简单）
./Script/gen_convert_url.sh -u 'https://example.com/sub?token=abc'

# 使用镜像后端并附加参数
./Script/gen_convert_url.sh -b mirror -u 'https://example.com/sub?token=abc' -p 'emoji=true' -p 'udp=true'

# 使用自定义后端 + 远程模板，保存为自定义文件名
./Script/gen_convert_url.sh -b 'https://your-backend.example.com' -u 'https://example.com/sub?token=abc' -c 'https://raw.githubusercontent.com/xxx/rules.ini' -f 'my-config.yaml'
```

脚本会自动下载配置文件并保存到项目根目录，同时输出转换链接和保存路径供参考。

### systemd 服务安装脚本

`Script/setup_mihomo_service.sh` 用于把 Mihomo 安装为系统服务（systemd）。

默认行为：

- 使用 `../mihomo` 作为可执行文件
- 使用项目根目录作为工作目录（要求存在 `config.yaml`）
- 写入 `/etc/systemd/system/mihomo.service`
- 执行 `daemon-reload` + `enable` + `restart`

使用示例：

```bash
# 一键安装并启动
sudo ./Script/setup_mihomo_service.sh

# 仅设置开机自启，不立即启动
sudo ./Script/setup_mihomo_service.sh --no-start

# 自定义服务名
sudo ./Script/setup_mihomo_service.sh -n mihomo-main
```

常用管理命令：

```bash
sudo systemctl status mihomo
sudo systemctl restart mihomo
sudo systemctl stop mihomo
sudo journalctl -u mihomo -f
```

---

## ⚙️ 配置进阶

### 配置来源约定

`config.yaml` 中大部分内容来自"订阅链接 -> 后端转换"的自动生成结果，主要包括：

- `proxies`
- `proxy-groups`
- `rules`（如果转换模板包含）

这些自动生成段在每次重新转换并覆盖配置时可能变化。

### 手动维护区（建议保留）

在配置顶部手动维护的关键项（转换后需要重新添加）：

```yaml
# 控制面板设置
external-controller: 0.0.0.0:9090
external-ui: ui
secret: ""  # 可选：面板访问密码

# TUN 强化配置（Ubuntu 优化版）
tun:
  enable: true
  stack: gvisor             # Ubuntu 必须用 gvisor（mixed/system 无法转发 TCP）
  auto-route: true
  auto-detect-interface: true
  mtu: 1500                 # 标准 MTU，兼容性最好
  dns-hijack:
    - any:53
    - tcp://any:53

# DNS 配置（普通解析，当前更推荐）
dns:
  enable: true
  ipv6: false
  listen: 0.0.0.0:53        # 若 53 被 systemd-resolved 占用，改为 0.0.0.0:1053

  # 兼容性过滤列表：保留给订阅或特殊服务使用，不启用 fake-ip 时通常不会生效
  fake-ip-filter:
    - "*.lan"
    - "*.srv.nintendo.net"
    - "*.stun.playstation.net"
    - xbox.*.microsoft.com
    - "*.xboxlive.com"
    - "*.teafone.com"
    - "*.sktswe.net"
    - rtc.goodfone.co.kr
    - "*.chattti.com"

  # 主 DNS：优先使用国内低延迟解析，DoT 作为加密备用
  nameserver:
    - 119.29.29.29
    - 223.5.5.5
    - tls://223.5.5.5:853
    - tls://223.6.6.6:853
    - tls://120.53.53.53
    - tls://1.12.12.12
```

> 建议把这段视为"本地定制区"，每次用订阅重新生成后都检查是否仍在。
> **Ubuntu 系统特别说明**：
> - **DNS 端口**：如果 `53` 未被占用可以直接使用；如果与 `systemd-resolved` 冲突，再改为 `1053`
> - **TUN stack**：**必须**使用 `gvisor`（`mixed` 和 `system` 存在 TCP 转发缺陷，会导致网络完全不可用）
> - **MTU**：使用标准值 `1500`（更高的值可能导致兼容性问题）
> - **DNS 模式**：当前不建议主动启用 `enhanced-mode: fake-ip`，普通解析更贴近系统真实 DNS 行为
> - **DNS 备份**：保留多个国内 DNS 和 DoT 备用，确保至少一种方式能工作

#### DNS 备选方案：fake-ip

普通解析作为当前推荐方案；如果遇到 DNS 污染明显、规则分流不准、或某些应用在普通解析下表现异常，可以临时切换回下面的 `fake-ip` 方案对比：

```yaml
dns:
  enable: true
  ipv6: false
  enhanced-mode: fake-ip
  listen: 0.0.0.0:1053
  fake-ip-range: 198.18.0.1/16

  fake-ip-filter:
    - '*.lan'
    - '*.local'
    - '+.ubuntu.com'
    - '+.debian.org'
    - 'pool.ntp.org'
    - '+.ntp.org'

  default-nameserver:
    - 223.5.5.5
    - 119.29.29.29
    - 114.114.114.114

  nameserver:
    - https://dns.alidns.com/dns-query
    - https://doh.pub/dns-query
    - 223.5.5.5

  fallback:
    - https://1.1.1.1/dns-query
    - https://dns.google/dns-query
    - tls://8.8.8.8:853

  fallback-filter:
    geoip: true
    geoip-code: CN
```

### 推荐更新流程（避免手动项被覆盖）

1. 通过订阅链接使用后端转换生成新配置。
2. 覆盖更新 `config.yaml`。
3. 对照本 README，将"手动维护区"补回（尤其是 `tun`、`external-controller`、`external-ui`）。
4. 启动 Mihomo 并检查日志是否正常。

---

## 🔧 故障排除

### 快速检查项

- 面板端口是否可访问：`9090`
- UI 目录是否存在：`ui/`
- DNS 劫持是否启用：`tun.dns-hijack`
- 规则模式是否符合预期：`mode: Rule`

### Ubuntu 系统常见问题

#### 1. DNS 端口冲突（最常见）

**症状**：启动 mihomo 后提示 `bind: address already in use` 或网络完全断开

**原因**：`systemd-resolved` 占用了 53 端口

**解决方案**：
```bash
# 方案 A：修改 config.yaml 中 DNS 监听端口（推荐）
# 将 listen: 0.0.0.0:53 改为 listen: 0.0.0.0:1053

# 方案 B：禁用 systemd-resolved（不推荐，可能影响系统）
sudo systemctl disable systemd-resolved
sudo systemctl stop systemd-resolved
```

#### 2. TUN 模式网络完全不可用（关键问题）

**症状**：启动 mihomo 后所有网络访问失败，包括百度等国内网站，关闭服务后恢复正常

**原因**：`mixed` 和 `system` 两种 TUN stack 存在 TCP 转发缺陷
- TUN 设备创建正常，路由表配置正确
- DNS 解析工作正常（普通解析）
- ICMP 流量可以通过（ping 成功）
- **但 TCP 连接无法建立**（HTTP/HTTPS 请求全部超时）

**解决方案**：
```yaml
# 修改 config.yaml 中 TUN stack 为 gvisor
tun:
  stack: gvisor  # 必须使用 gvisor，mixed/system 无法转发 TCP
  mtu: 1500      # 使用标准 MTU
```

**诊断方法**：
```bash
# 启动服务后测试
sudo systemctl start mihomo
sleep 3

# 1. 检查 TUN 设备（应该存在）
ip link show | grep Meta

# 2. 测试 ICMP（应该成功）
ping -c 2 223.5.5.5

# 3. 测试 TCP（如果失败说明是 stack 问题）
curl -I http://www.baidu.com

# 如果 ping 通但 curl 超时，说明 TCP 转发失败，需要切换到 gvisor
```

#### 3. 系统更新失败（apt update 报错）

**症状**：运行 `sudo apt update` 时提示无法解析域名或连接超时

**原因**：常见原因是 DNS 端口冲突、上游 DNS 不可用，或启用了 `enhanced-mode: fake-ip` 后系统域名被 fake-ip 影响

**解决方案**：
```yaml
# 推荐先使用普通解析，不主动启用 enhanced-mode: fake-ip
dns:
  enable: true
  ipv6: false
  listen: 0.0.0.0:53  # 若 53 冲突则改为 0.0.0.0:1053
  nameserver:
    - 119.29.29.29
    - 223.5.5.5
    - tls://223.5.5.5:853
```

#### 4. 服务启动失败（权限问题）

**症状**：systemd 服务无法启动，日志显示权限错误

**原因**：TUN 模式需要 root 权限

**解决方案**：
```bash
# 确保服务以 root 身份运行
sudo ./Script/setup_mihomo_service.sh

# 检查服务配置
sudo systemctl cat mihomo | grep User
# 应该显示 User=root
```

### 常见问题

- 若系统 DNS/网络管理器与 TUN 冲突，优先检查系统 DNS 服务设置（如 `systemd-resolved`）与防火墙转发规则。
- 若测速或连通性异常，可先临时切换 `proxy-groups` 到单节点排查。
- 若 Tailscale 等虚拟内网无法访问，参考"第六步"中的虚拟内网配置提示。
- 当前 DNS 写法的主要隐患：普通 UDP DNS 可能被运营商劫持或污染；未配置国外 fallback 时，部分境外域名解析质量依赖当前上游；监听 `0.0.0.0:53` 时如果开放到局域网，需要注意不要暴露成不受控的 DNS 服务。

### 调试命令

```bash
# 查看服务状态
sudo systemctl status mihomo

# 查看实时日志
sudo journalctl -u mihomo -f

# 检查 DNS 端口占用
sudo ss -tulnp | grep :53
sudo ss -tulnp | grep :1053

# 检查路由表
ip route show

# 测试 DNS 解析
nslookup google.com 127.0.0.1

# 检查 TUN 设备
ip link show | grep tun
```
