# Mihomo 本地配置说明

本目录用于运行 Mihomo（含 Web UI）并管理由订阅转换生成的配置。

## 目录结构

- `config.yaml`：主配置文件（核心）
- `mihomo`：Mihomo 可执行文件
- `source/`：订阅/规则来源相关文件
- `country.mmdb`、`geoip.metadb`、`geoip.dat`、`GeoSite.dat`：地理库和规则数据库

## 配置来源约定

`config.yaml` 中大部分内容来自“订阅链接 -> 肥羊后端转换”的自动生成结果，主要包括：

- `proxies`
- `proxy-groups`
- `rules`（如果转换模板包含）

这些自动生成段在每次重新转换并覆盖配置时可能变化。

## 手动维护区（建议保留）

你当前在配置顶部手动维护的关键项主要是：

- 控制与面板：
  - `external-controller: 0.0.0.0:9090`
  - `external-ui: ui`
- `tun` 强化配置：
  - `enable: true`
  - `stack: gvisor`
  - `auto-route: true`
  - `auto-detect-interface: true`
  - `mtu: 1500`
  - `strict-route: true`
  - `dns-hijack`（`any:53` 与 `tcp://any:53`）

> 建议把这段视为“本地定制区”，每次用订阅重新生成后都检查是否仍在。

## 推荐更新流程（避免手动项被覆盖）

1. 通过订阅链接在肥羊后端生成新配置。
2. 覆盖更新 `config.yaml`。
3. 对照本 README，将“手动维护区”补回（尤其是 `tun`、`external-controller`、`external-ui`）。
4. 启动 Mihomo 并检查日志是否正常。

## 启动示例

在当前目录运行：

```bash
./mihomo -d .
```

如需 root 权限（例如接管路由/TUN）：

```bash
sudo ./mihomo -d .
```

## 快速检查项

- 面板端口是否可访问：`9090`
- UI 目录是否存在：`ui/`
- DNS 劫持是否启用：`tun.dns-hijack`
- 规则模式是否符合预期：`mode: Rule`

## 备注

- 若系统 DNS/网络管理器与 TUN 冲突，优先检查系统 DNS 服务设置（如 `systemd-resolved`）与防火墙转发规则。
- 若测速或连通性异常，可先临时切换 `proxy-groups` 到单节点排查。

## 订阅转换链接生成脚本

根目录的 `Script/` 目录已提供脚本：`Script/gen_convert_url.sh`

用于把“原始订阅链接”拼接成可直接使用的转换链接，支持：

- 官方后端：`https://sub.fndroid.com`
- 镜像后端：`https://api.v1.mk`
- 自定义后端地址
- 附加任意参数（如 `emoji=true`、`udp=true` 等）

示例：

```bash
# 使用官方后端（默认）
./Script/gen_convert_url.sh -u 'https://example.com/sub?token=abc'

# 使用镜像后端并附加参数
./Script/gen_convert_url.sh -b mirror -u 'https://example.com/sub?token=abc' -p 'emoji=true' -p 'udp=true'

# 使用自定义后端 + 远程模板
./Script/gen_convert_url.sh -b 'https://your-backend.example.com' -u 'https://example.com/sub?token=abc' -c 'https://raw.githubusercontent.com/xxx/rules.ini'
```

脚本会输出一行完整转换链接，可直接粘贴到客户端或后续流程中使用。

## systemd 服务安装脚本

`Script/setup_mihomo_service.sh` 用于把 Mihomo 安装为系统服务（systemd）。

默认行为：

- 使用 `../mihomo` 作为可执行文件
- 使用项目根目录作为工作目录（要求存在 `config.yaml`）
- 写入 `/etc/systemd/system/mihomo.service`
- 执行 `daemon-reload` + `enable` + `restart`

示例：

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

## 官方资源一键更新脚本

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
