# Mihomo 订阅自动更新脚本

该目录提供 5 个脚本：

- `detect_subscription_format.sh`：判断订阅是 `clash` 还是 `base`。
- `convert_subscription_to_config.sh`：仅做下载和转换，输出为新配置文件。
- `update_from_subscription.sh`：手动拉取订阅并覆盖 `config.yaml`（会先校验并备份）。
- `install_user_timer.sh`：安装 user 级 systemd 定时任务（默认每 6 小时更新）。
- `uninstall_user_timer.sh`：卸载定时任务。

## 快速使用

先赋予执行权限：

```bash
cd ~/.config/mihomo/scripts/subscription
chmod +x *.sh
```

手动更新一次：

```bash
./update_from_subscription.sh "你的订阅链接"
```

仅识别订阅格式：

```bash
./detect_subscription_format.sh "你的订阅链接"
```

仅转换为配置文件（不覆盖当前 config.yaml）：

```bash
./convert_subscription_to_config.sh "你的订阅链接" "./config.converted.yaml"
```

安装自动更新定时任务：

```bash
./install_user_timer.sh "你的订阅链接"
```

查看定时任务状态：

```bash
systemctl --user status mihomo-subscription-update.timer
systemctl --user list-timers | grep mihomo-subscription-update
```

卸载定时任务：

```bash
./uninstall_user_timer.sh
```

## 行为说明

- 下载后会先用本目录下的 `mihomo` 二进制执行配置校验。
- 校验通过才覆盖 `config.yaml`。
- 旧配置会备份到 `~/.config/mihomo/backups/`。
- 若检测到 `mihomo.service` 正在运行，会尝试重启服务使新配置生效。
- 自动处理分组：如果缺少 `♻️ 自动选择` 或 `🔁 Fallback`，会自动补齐。
- `♻️ 自动选择` 与 `🔁 Fallback` 会自动排除香港/台湾节点（按名称和服务器关键字匹配）。
