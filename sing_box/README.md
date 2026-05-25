# sing-box 本地配置说明

本目录用于独立运行 sing-box，并承载从根目录 `config.yaml` 转换生成的 sing-box 配置。下载缓存、核心文件、Web UI 和生成配置都放在 `sing_box/` 内，避免和 Mihomo 目录互相污染。

## 目录结构

- `config.json`：转换生成的 sing-box 配置文件
- `sing-box`：sing-box 可执行文件
- `sing-box.version`：当前下载的 sing-box 版本
- `ui/`：Web UI 静态资源，供 Clash API 通过 `/ui` 访问
- `source/downloads/`：sing-box core 和 Web UI 下载缓存
- `Script/update_sing_box_core.sh`：下载并更新 sing-box core 和 Web UI
- `Script/setup_sing_box_service.sh`：注册或删除 sing-box systemd 服务
- `Script/Enhance/convert_mihomo_config.py`：把根目录 Mihomo `config.yaml` 转成 sing-box `config.json`

## 快速开始

赋予脚本执行权限：

```bash
chmod +x ./sing_box/Script/*.sh ./sing_box/Script/Enhance/*.py
```

下载 sing-box core 和 Web UI：

```bash
./sing_box/Script/update_sing_box_core.sh
```

转换当前 Mihomo 配置：

```bash
./sing_box/Script/Enhance/convert_mihomo_config.py
```

检查配置：

```bash
./sing_box/sing-box check -c ./sing_box/config.json
```

启动 sing-box：

```bash
./sing_box/sing-box run -c ./sing_box/config.json
```

## 系统服务

注册为 systemd 服务并立即启动：

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

## Web UI

转换脚本会把根目录 `config.yaml` 中的 `external-controller` 和 `external-ui` 转成 sing-box 的 `experimental.clash_api` 配置。

局域网访问通常需要：

```json
{
  "experimental": {
    "clash_api": {
      "external_controller": "0.0.0.0:9090",
      "external_ui": "ui",
      "default_mode": "Rule"
    }
  }
}
```

启动后访问：

```text
http://<LAN-IP>:9090/ui
```

如果开放到局域网，建议在配置里设置 `secret`，避免同网段设备直接控制代理。

## 注意事项

- 转换脚本优先支持当前仓库实际使用的 Mihomo 配置结构：`ss` 节点、`select` 分组、常见 Clash 规则、DNS、TUN 和 Clash API。
- 生成的 `sing_box/config.json` 包含节点信息，已在根目录 `.gitignore` 中忽略。
- `sing_box/ui/`、`sing_box/sing-box`、`sing_box/source/downloads/` 都是生成产物，已忽略。
