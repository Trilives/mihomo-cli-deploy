# Mihomo (Meta) 本地配置指南

本项目提供了一套完整的 Mihomo (原 Clash.Meta) 本地运行环境，包含核心二进制文件、Web UI 面板及自动化维护脚本。通过订阅转换机制，实现高效、灵活的规则管理。

## 目录结构说明

| 路径 | 说明 | 来源 |
| :--- | :--- | :--- |
| `mihomo` | Mihomo 核心二进制文件 | 官方 GitHub Release |
| `config.yaml` | 主配置文件 (核心) | 手动维护 + 订阅转换覆盖 |
| `ui/` | Web UI 静态资源 (`metacubexd`) | 官方 GitHub Release |
| `source/` | 原始订阅链接、规则备份及下载暂存 | 手动维护 |
| `*.dat` / `*.mmdb` | 地理位置数据库与规则集 | MetaCubeX 规则库 |

---

## 配置架构与维护

### 1. 动态生成区 (由订阅转换覆盖)
通过“肥羊后端”或其他转换工具生成的配置，通常包含以下部分：
* **`proxies`**: 节点列表
* **`proxy-groups`**: 策略组逻辑
* **`rules`**: 流量分流规则

### 2. 本地静态维护区 (核心运行参数)
**重要：** 每次覆盖 `config.yaml` 后，请务必确认以下参数已正确配置，以确保 TUN 模式和 Web 面板正常工作：

```yaml
# 控制面板设置
external-controller: 0.0.0.0:9090
external-ui: ui
secret: "" # 可选：面板访问密码

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
```

---

## 自动化脚本工具集

项目在 `Script/` 目录下提供了高效的运维脚本：

### 🔗 订阅链接生成 (`gen_convert_url.sh`)
将原始订阅地址转换为 Mihomo 可识别的完整配置链接。
* **用法**: `./Script/gen_convert_url.sh -u 'YOUR_SUB_URL' -b mirror`
* **支持**: 官方/镜像后端切换、自定义远程模板、附加参数 (Emoji, UDP 等)。

### 📥 核心组件更新 (`update_core_assets.sh`)
一键更新 Mihomo 核心、Web UI 及所有地理库文件。
* **用法**: `./Script/update_core_assets.sh`
* **流程**: 下载至 `source/downloads/` → 解压校验 → 部署至根目录。

### ⚙️ 系统服务安装 (`setup_mihomo_service.sh`)
将 Mihomo 注册为 systemd 守护进程，实现开机自启。
* **用法**: `sudo ./Script/setup_mihomo_service.sh`
* **管理**: 
    * 启动: `sudo systemctl start mihomo`
    * 日志: `sudo journalctl -u mihomo -f`

---

## 快速上手流程

1.  **初始化环境**: 
    运行 `./Script/update_core_assets.sh` 下载必要文件。
2.  **生成配置**: 
    使用 `gen_convert_url.sh` 获取转换后的 YAML 内容，并保存为 `config.yaml`。
3.  **注入本地参数**: 
    将上文 [手动维护区](#2-本地静态维护区-核心运行参数) 的内容补回 `config.yaml` 顶部。
4.  **权限检查**:
    确保 `mihomo` 文件具有执行权限：`chmod +x mihomo`。
5.  **启动服务**:
    * 前台调试: `sudo ./mihomo -d .`
    * 后台运行: 运行系统服务安装脚本后使用 `systemctl` 管理。

---

## 故障排查与提示

* **DNS 冲突**: 若 TUN 模式启动失败，请检查系统是否占用了 53 端口 (如 `systemd-resolved`)。
* **Web 面板**: 启动后通过浏览器访问 `http://127.0.0.1:9090/ui`。
* **权限说明**: 使用 TUN 模式接管系统流量必须以 `sudo` 或 `root` 权限运行。
* **数据隔离**: 建议将原始订阅 URL 存储在 `source/` 目录下的文本文件中，不要直接硬编码在脚本内。