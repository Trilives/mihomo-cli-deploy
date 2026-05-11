# Mihomo 本地配置说明

本目录用于运行 Mihomo（含 Web UI）并管理由订阅转换生成的配置。

## 目录结构(均由脚本下载，初始仓库没有)

- `config.yaml`：主配置文件（核心）
- `mihomo`：Mihomo 可执行文件
- `ui/`：Web UI 静态资源（`external-ui: ui`）
- `source/`：订阅/规则来源相关文件
- `country.mmdb`、`geoip.metadb`、`geoip.dat`、`GeoSite.dat`：地理库和规则数据库

---

## 🚀 快速开始（从零开始）

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

**方式 A：使用订阅链接（推荐）**

直接运行脚本，自动生成并保存配置文件：

```bash
./Script/gen_convert_url.sh -u 'https://your-subscribe-link'
```

脚本会输出转换链接和保存路径，配置文件自动保存到 `config.yaml`。

如需自定义参数或文件名：
```bash
./Script/gen_convert_url.sh -u 'https://your-subscribe-link' -b mirror -p 'emoji=true' -f 'config.yaml'
```

**方式 B：手动编写配置**

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

# TUN 配置（可选但推荐）
tun:
  enable: true
  stack: gvisor
  auto-route: true
  auto-detect-interface: true
  dns-hijack:
    - any:53
    - tcp://any:53

# DNS 配置
dns:
  enable: true
  enhanced-mode: fake-ip
  listen: 0.0.0.0:53
  default-nameserver:
    - 8.8.8.8
    - 1.1.1.1
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

**局域网访问（如果 `external-controller` 配置为 `0.0.0.0:9090`）：**

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

# TUN 强化配置 (推荐)
tun:
  enable: true
  stack: gvisor
  auto-route: true
  auto-detect-interface: true
  mtu: 1500
  strict-route: true
  dns-hijack:
    - any:53
    - tcp://any:53

# DNS 配置
dns:
  enable: true
  enhanced-mode: fake-ip
```

> 建议把这段视为"本地定制区"，每次用订阅重新生成后都检查是否仍在。

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

### 常见问题

- 若系统 DNS/网络管理器与 TUN 冲突，优先检查系统 DNS 服务设置（如 `systemd-resolved`）与防火墙转发规则。
- 若测速或连通性异常，可先临时切换 `proxy-groups` 到单节点排查。
