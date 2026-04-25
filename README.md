# Mihomo 本地配置仓库

这是一个可直接运行的 Mihomo（Meta）本地目录，包含：

- 可执行文件
- 主配置文件
- Geo 数据文件
- 本地 Web UI 静态资源

当前环境验证信息：

- Mihomo 版本：`Mihomo Meta v1.19.24 linux amd64`
- Web 控制端口：`9090`
- HTTP 代理端口：`7890`
- SOCKS5 代理端口：`7891`

## 目录结构

```text
.
├── mihomo                      # Mihomo 可执行文件
├── config.yaml                 # 主配置（节点、规则、DNS、分组等）
├── config.yaml.bak.*           # 备份配置
├── geoip.metadb                # GeoIP 数据库
├── GeoIP.dat                   # 兼容数据文件
├── cache.db                    # 运行缓存
└── ui/                         # external-ui 指向的本地面板静态文件
```

## 快速开始（Linux）

### 1) 进入目录并赋予执行权限

```bash
cd ~/.config/mihomo
chmod +x ./mihomo
```

### 2) 校验配置文件

```bash
./mihomo -t -f ./config.yaml
```

### 3) 启动 Mihomo（前台）

```bash
./mihomo -d . -f ./config.yaml
```

说明：

- `-d .` 指定当前目录为工作目录（读取 Geo 数据、缓存等）
- `-f ./config.yaml` 指定配置文件路径

### 4) 后台运行（可选）

使用 `tmux`：

```bash
tmux new -s mihomo
./mihomo -d . -f ./config.yaml
# 按 Ctrl+b 再按 d 退出会话（进程保持运行）
```

重新进入会话：

```bash
tmux attach -t mihomo
```

## 使用 systemd 作为系统服务启动

适用于希望开机自启、崩溃自动拉起、统一用 `systemctl` 管理的场景。

### 1) 创建服务文件

```bash
sudo tee /etc/systemd/system/mihomo.service >/dev/null <<'EOF'
[Unit]
Description=Mihomo Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/trlives/.config/mihomo
ExecStart=/home/trlives/.config/mihomo/mihomo -d /home/trlives/.config/mihomo -f /home/trlives/.config/mihomo/config.yaml
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
```

如果你的目录不是 `/home/trlives/.config/mihomo`，请替换为实际路径。

### 2) 重新加载并启动

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mihomo
```

### 3) 常用管理命令

```bash
sudo systemctl status mihomo
sudo systemctl restart mihomo
sudo systemctl stop mihomo
sudo journalctl -u mihomo -f
```

### 4) 关闭开机自启（可选）

```bash
sudo systemctl disable --now mihomo
```

说明：

- 当前配置监听了 `53` 端口（`dns.listen: 0.0.0.0:53`），通常需要 root 权限或额外能力才能绑定。
- 若服务启动失败，优先查看 `journalctl -u mihomo -n 200` 的报错。

## 面板与接口

当前配置中：

- `external-controller: 0.0.0.0:9090`
- `external-ui: ui`

启动后可通过以下地址访问：

- 控制接口：`http://127.0.0.1:9090`
- 面板：`http://127.0.0.1:9090/ui`

如果你在公网环境使用，请务必设置 `secret` 并配合防火墙限制访问。

## 常见操作

### 查看版本

```bash
./mihomo -v
```

### 仅覆盖控制端口（临时）

```bash
./mihomo -d . -f ./config.yaml -ext-ctl 127.0.0.1:9091
```

### 仅覆盖面板目录（临时）

```bash
./mihomo -d . -f ./config.yaml -ext-ui ./ui
```

## 安全建议

`config.yaml` 中通常包含节点地址、认证信息或订阅敏感内容。建议：

- 不要将真实配置直接公开到公共仓库
- 分享配置时先脱敏（server、password、token、订阅 URL）
- 可额外维护 `config.example.yaml` 作为公开示例

## 故障排查

### 端口占用

```bash
ss -lntp | grep -E ':(53|7890|7891|9090)'
```

### 配置语法错误

```bash
./mihomo -t -f ./config.yaml
```

### DNS 53 端口绑定失败

常见原因是系统 DNS 服务已占用 53 端口。可选方案：

- 修改配置中的 `dns.listen` 到其他端口（例如 `1053`）
- 或停止/调整系统 DNS 服务

## 维护建议

- 在每次替换订阅后先执行一次配置校验
- 保留可回滚备份（当前仓库已保留 `config.yaml.bak.*`）
- 升级二进制后执行一次版本与配置兼容性检查

## Git 同步备份（使用 .gitignore）

为了把配置仓库同步到 Git，同时避免提交体积大/可再下载的二进制文件，当前采用了 `.gitignore` 策略：

- 忽略：`mihomo`、`Country.mmdb`、`geoip.dat`、缓存与备份文件等
- 保留同步：`config.yaml`、脚本、说明文档与 UI 目录

上游来源约定：

- `Country.mmdb` / `geoip.dat`：`https://github.com/Loyalsoldier/geoip`
- `mihomo`：`https://github.com/MetaCubeX/mihomo`（官方仓库）

### 一键拉取被忽略资源

```bash
cd ~/.config/mihomo
chmod +x ./scripts/sync/sync_assets.sh
./scripts/sync/sync_assets.sh
```

### Git 同步示例

```bash
cd ~/.config/mihomo
git init
git add .
git commit -m "backup: mihomo config and scripts"
```

说明：`git add .` 会自动跳过 `.gitignore` 中列出的文件。
