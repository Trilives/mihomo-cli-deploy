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
- `Script/download_sing_box_subscription.sh`：通过 subconverter 后端把订阅转换为 sing-box `config.json`
- `Script/Enhance/convert_mihomo_config.py`：本地兜底转换，把根目录 Mihomo `config.yaml` 转成 sing-box `config.json`

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

本地兜底转换当前 Mihomo 配置：

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

## Web UI

后端转换得到的配置不一定包含 Web UI 设置。需要局域网访问 UI 时，确认 `sing_box/config.json` 中包含 `experimental.clash_api`。

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

- 默认推荐使用 `Script/download_sing_box_subscription.sh` 走 subconverter 后端生成 sing-box 配置。
- `https://sub-web.wcc.best` 和 `https://sublink.dev` 是前端页面，不一定能直接作为脚本 API 后端；脚本需要真实的 subconverter 后端，例如自建 `http://127.0.0.1:25500`。
- 本地 Python 转换脚本只是兜底方案，优先支持当前仓库实际使用的 Mihomo 配置结构：`ss` 节点、`select` 分组、常见 Clash 规则、DNS、TUN 和 Clash API。
- 生成的 `sing_box/config.json` 包含节点信息，已在根目录 `.gitignore` 中忽略。
- `sing_box/ui/`、`sing_box/sing-box`、`sing_box/source/downloads/` 都是生成产物，已忽略。
