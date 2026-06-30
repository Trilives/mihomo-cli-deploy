# Mihomo CLI 部署系统

在 Linux 上交互式部署 / 管理 **Mihomo（Clash.Meta）** 的命令行系统。一个入口 `./mihomo.sh`，
全流程交互完成：**初始化 / 更改配置 / 网络测试 / 卸载**（更新另有命令行子命令）。直接消费机场
原生 Clash 配置，不重写分流——成熟机场开箱即用。

- **零第三方依赖**：只用系统自带 `python3` 标准库，不装 pip 包、不用虚拟环境
  （部署机常无代理，装包慢/易失败）。Clash YAML 用内置 `yamlmini` 解析（替代 PyYAML）。
- **自绘 TUI**：方向键导航、反显高亮、边框盒子；选项多于一屏时滑动显示；非 TTY 自动回退编号菜单。
- **随时可中止可回退**：任意步骤按 **ESC** 取消，已应用的改动自动回滚。
- **按需提权**：普通用户启动，需要 root 时自动 `sudo`（也可 `sudo ./mihomo.sh`）。

架构细节见 [ARCHITECTURE.md](ARCHITECTURE.md)。

> 想用 **sing-box**？见姊妹项目
> [singbox_cli_ui](https://github.com/Trilives/singbox_cli_ui)：同一套交互骨架的 sing-box 版，
> 含本地 clash→singbox 转换器与精细分流定制层。

## 快速开始

```bash
chmod +x ./mihomo.sh
./mihomo.sh
```

进入主菜单后选择「初始化」，按提示完成（多数项**直接回车**即用推荐默认）：

1. 填下载代理（留空=直连；用于加速下载核心/UI/geo）。
2. 选 **TUN 模式**（默认开=整机透明代理；关=纯代理）。
3. （可选）开启局域网代理 `allow-lan`，并按需放行防火墙 7890。
4. （可选）开放 Web UI 到局域网。
5. 下载 Mihomo 核心 + MetaCubeXD 面板 + geo 数据。
6. 添加首个订阅（Clash/Mihomo YAML 直链；通用订阅可选经 subconverter 转换）。
7. 注册 systemd 服务，（可选）网络自愈、每周更新。
8. （可选）立即切换 / 固定节点。

## 命令行（非交互，便于脚本/定时器）

```bash
./mihomo.sh init       # 初始化（首次部署）
./mihomo.sh modify     # 更改配置（订阅 / 定制层 / 节点 / 服务 / 自愈 / 定时器）
./mihomo.sh nettest    # 网络测试（延迟 + 出口 IP）
./mihomo.sh update     # 更新 核心 / UI / geo 并同步重启
./mihomo.sh uninstall  # 卸载 服务 / 定时器 / 产物 / 状态
```

## 订阅行为

Mihomo 直接使用 **Clash/Mihomo YAML** 订阅链接，无需转换为其它格式——这是与 sing-box 版
最大的不同。两种来源：

| 来源 | 说明 |
| --- | --- |
| **Clash/Mihomo 直链**（★推荐） | YAML，本地直取、不外泄凭证、兼容性最好 |
| **通用 base64** | 经云端 subconverter 转为 Clash/Mihomo YAML 再本地使用 |

- **默认保留机场原始 proxy-groups**，不重写分流（成熟机场配置直接可用）。
- 可**选**在新增/重建订阅时追加 Mihomo 特有的 **SG / HK** url-test/fallback 地区组。
- 订阅命名保存于 `state/subscriptions/<name>/`，可随时**切换生效订阅**。
- **订阅链接变化时**（新增设为生效 / 切换 / 刷新生效订阅）完成后会交互提示是否进入「切换 / 固定节点」。

> 隐私：base64 走第三方 subconverter 会发送节点凭证。默认后端 `https://api.v1.mk`，
> 隐私敏感者可在「定制层」改为自建后端。

## 定制层

「更改配置 → 编辑 Mihomo 定制层」交互式增删改：**TUN 开关 / 协议栈**、局域网代理 `allow-lan`、
Web UI 暴露、SG/HK 地区组及关键词、Clash API 监听、UI 目录、自动 secret、下载代理、
subconverter 后端与额外参数、GitHub 加速。持久化于 `state/customize.json`。

编辑器为**缓冲式**：列出全部字段（常用项前置），按 `esc`（保存并退出）才写盘，`Ctrl-R` 放弃本次修改；
字段多于一屏时菜单滑动显示。

## Web UI

面板默认仅本机 `http://127.0.0.1:9090/ui`。远程查看用 SSH 端口转发：

```bash
ssh -N -L 9090:127.0.0.1:9090 user@server
```

确需开放局域网时在「定制层」开启 Web UI 暴露（务必设 secret + 防火墙）。

## 目录结构

```
mihomo-cli-deploy/
├── mihomo.sh               # 瘦入口：环境检查 → 调起 Python CLI
├── lib/mihomo_deploy/      # Python 主体（零依赖，模块可单独 -m 调用）
├── templates/              # systemd unit / healthcheck 模板
├── tests/                  # yamlmini / 订阅管理 / 定制层 / 节点选择 单测
└── state/                  # 运行期产物（gitignore：核心/UI/geo/订阅/配置）
```

## 验证

```bash
PYTHONPATH=lib python3 -m py_compile $(find lib tests -name '*.py' -print)
PYTHONPATH=lib python3 -m unittest discover -s tests
```

## 环境要求

Linux + systemd；系统自带 `python3`（≥3.10）、`curl`、`tar`。TUN/服务需 root（自动 sudo）。

## 第三方资产与致谢

本项目**不打包任何二进制/UI/geo 数据**，全部运行时从上游按需下载，各自保留原始许可证：

| 资产 | 来源 | 用途 |
| --- | --- | --- |
| Mihomo 核心 | [MetaCubeX/mihomo](https://github.com/MetaCubeX/mihomo)（GPL-3.0） | 代理核心 |
| Web 面板 | [MetaCubeX/metacubexd](https://github.com/MetaCubeX/metacubexd) | Clash API 面板 |
| geo 数据 | [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat) | 分流数据 |
| 订阅转换后端 | 公共 [subconverter](https://github.com/asdlokj1qpi23/subconverter) 实例 | base64 来源解析 |

## 许可证

本项目代码以 [MIT](LICENSE) 许可证发布。上述第三方资产不随本仓库分发，使用时受其各自许可证约束。
