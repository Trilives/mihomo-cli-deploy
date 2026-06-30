# Mihomo CLI 部署系统 · 架构

交互式 CLI 部署 / 管理 Mihomo（Clash.Meta）的零依赖系统。一个入口 `mihomo.sh`，交互主菜单为
**初始化 / 更改配置 / 网络测试 / 卸载**，另有 `update` 命令行子命令。本文描述已落地的架构；上手用法见 [README](README.md)。

> 姊妹项目：[singbox_cli_ui](https://github.com/Trilives/singbox_cli_ui) —— 同一套交互骨架的
> sing-box 版。本项目由其重构而来，**最大差异在订阅层**（见 §5）。

---

## 1. 设计取向

| 决策 | 选择 | 理由 |
| --- | --- | --- |
| 语言 | Python 为主，`mihomo.sh` 仅瘦入口 | 模块化、可单独 `-m` 调用 |
| 运行时依赖 | **仅系统 `python3` 标准库** | 部署机常无代理，pip 装包慢/易失败 |
| YAML 解析 | 自带 `yamlmini`（替代 PyYAML） | 零依赖解析 Clash 订阅 |
| 配置模型 | **直接消费机场原生 Clash 配置** | Mihomo 即 Clash.Meta，无需转换格式 |
| 网络下载 | 外部 `curl` 子进程 | 稳定 |
| 界面 | stdlib 自绘 TUI（termios + ANSI） | 零依赖；非 TTY 自动回退编号菜单 |
| 提权 | 按需 `sudo`（`shell.run_root`） | 普通用户启动，需 root 时自动提权 |

**与 sing-box 版的关键分野**：sing-box 版要从零生成整份 sing-box JSON（含本地 clash→singbox
转换器、AI/流媒体/直连分流、引导 DNS 等定制层）；Mihomo 版**直接用机场的 Clash YAML**，只在
其顶层注入运行时设置、可选追加地区组——因此**不含转换器**（无 `convert.py`/`b64.py`/`detect.py`），
定制字段也精简为 Mihomo 自身需要的那些。

**范围**：仅 Linux + systemd；单内核（Mihomo）；单 active 订阅模型。

---

## 2. 目录结构

```
mihomo-cli-deploy/
├── mihomo.sh                   # 瘦入口：环境检查 → PYTHONPATH=lib exec python3 -m mihomo_deploy
├── ARCHITECTURE.md             # 本文
├── README.md
├── LICENSE                     # MIT
├── lib/mihomo_deploy/          # Python 主体（模块可单独 -m 调用）
│   ├── __main__.py             # 入口分发：init / modify / nettest / update / uninstall
│   ├── paths.py                # 统一路径常量
│   ├── shell.py                # 子进程 / 日志 / 彩色输出 / run_root 提权
│   ├── errors.py               # 共享异常（Cancelled / SaveExit）
│   ├── keys.py                 # 可中断终端输入（termios 原始模式 + 等宽处理）
│   ├── menu.py                 # 自绘 TUI 组件：select / multiselect / ask / confirm（含滚动视口）
│   ├── tx.py                   # 事务 / 回退引擎（ESC 或异常时 LIFO 回滚）
│   ├── yamlmini.py             # 标准库实现的极简 Clash YAML 解析器
│   ├── flows/                  # 入口流程编排
│   │   ├── init.py             # 初始化全流程
│   │   ├── modify.py           # 更改配置全流程（会话级事务）
│   │   ├── nettest.py          # 网络测试（延迟 + 出口 IP）
│   │   ├── uninstall.py        # 卸载（多选清单）
│   │   └── common.py           # 流程间共享的交互
│   ├── core.py                 # 下载/更新 核心 + MetaCubeXD UI + geo 数据
│   ├── service.py              # systemd 注册/删除/重启，同步配置到 /etc/mihomo/
│   ├── resilience.py           # 网络自愈（NM 钩子 + watchdog 定时器）
│   ├── timer.py                # 每周自动更新定时器
│   ├── node_select.py          # 交互切换/固定节点（运行时 Clash API + 实时测速）
│   ├── proxyenv.py             # TUN 关闭时写入 shell 代理环境变量
│   ├── firewall.py             # 局域网代理时放行/撤销防火墙端口
│   ├── customize.py            # 定制层：顶层 Clash 设置注入 + SG/HK 地区组 + 缓冲式字段编辑
│   └── subscription/           # 订阅子系统（无转换器）
│       ├── manager.py          # 命名订阅 增/删/改名/切换/列表/刷新/重建
│       └── fetch.py            # 直取 Clash YAML / 经 subconverter 转换
├── templates/                  # systemd unit / healthcheck 模板
├── tests/                      # yamlmini / 订阅管理 / 定制层 / 节点选择 单测
└── state/                      # 运行期产物（.gitignore，全部本地生成）
```

`state/` 关键文件：`subscriptions/<name>/{meta.json,raw.yaml,config.yaml}`、`active`（当前生效
订阅名）、`config.yaml`（生效配置 = active 订阅的拷贝）、`customize.json`（定制层）。根级
`mihomo`、`config.yaml`、`ui/`、`*.mmdb` 等为 CLI 生成的兼容拷贝，均被 Git 忽略。

---

## 3. 定制层 `state/customize.json`

经「更改配置 → 编辑 Mihomo 定制层」交互式增删改；缓冲式编辑器（列出全部字段、常用项前置、
`esc` 保存写盘、`^R` 放弃、超一屏滑动）。字段分三类：

- **列表**：`sg_keywords` / `hk_keywords` / `subconverter_extra_params`。
- **开关**：`enable_tun` / `allow_lan` / `lan_panel` / `generate_sg_groups` /
  `generate_hk_groups` / `generate_secret`。
- **标量**：`download_proxy` / `subconverter_backend` / `github_mirror` / `tun_stack` /
  `external_controller` / `external_ui`。

`allow_lan` 开关变化时按需放行/撤销防火墙 7890。注意：这里**没有** sing-box 版的分流/DNS/
路由字段——那些在 Mihomo 下由机场原生 Clash 配置承载。

---

## 4. 交互流程

```
交互主菜单 → 初始化 / 更改配置 / 网络测试 / 卸载    （update 为命令行子命令）
```

- **初始化**（`flows/init.py`）：下载代理 → TUN/局域网/面板开关 → 下载核心/UI/geo →
  添加首个订阅 → 注册服务 →（可选）每周更新 / 网络自愈 →（可选）切换/固定节点。
- **更改配置**（`flows/modify.py`）：整个会话包在 `Transaction` 里——配置类改动临时，`esc`
  保存提交、`^R` 回退；系统类操作（节点切换 / 更新 / 服务 / 自愈 / 定时器）标 `※即时`。
  **订阅链接变化时**（新增设为生效 / 切换 / 刷新生效订阅）完成后交互提示是否进入「切换 / 固定节点」。
- **网络测试 / 卸载**：与 sing-box 版一致（并发测延迟 + 出口 IP；多选清单逐项卸载）。

---

## 5. 订阅子系统（核心差异）

Mihomo 即 Clash.Meta，订阅本身就是目标格式，**无需转换器**。两种来源：

| 来源 | 路径 | 隐私 |
| --- | --- | --- |
| **Clash/Mihomo 直链**（★推荐） | `fetch.direct →` 直接落地为 `config.yaml` | 全程本地 |
| **通用 base64** | `fetch.converted →` subconverter(target=clash) → 落地 | 凭证发往后端 |

`manager.py` 流程：拉取 → 写 `raw.yaml` → 由 `_write_config` 落地 `config.yaml`（可选
`customize.add_region_groups` 追加 SG/HK 组）→ 统计节点数写 `meta.json`。切换/刷新生效订阅时
拷贝到 `config.yaml`/`/etc/mihomo` 并同步重启服务。`rebuild` 用本地 `raw.yaml` 重新落地（不重新拉取）。

**机场原生分组默认保留**：`add_region_groups` 仅在 proxies 命中关键词时**新增** `SG-Auto`/
`SG-Fallback`/`HK-Auto`/`HK-Fallback` 并插到首个 select 组前，不改动机场原有 proxy-groups。

`customize.ensure_runtime_settings` 只编辑订阅 YAML 的**顶层键**（`allow-lan` /
`external-controller` / `external-ui` / `mode` / `secret` / `tun` 块），避免解析重写整份订阅，
最大限度保留机场原文。

---

## 6. 可中断与回退（ESC + 事务）

与姊妹项目一致：任意交互处 `ESC`（或 Ctrl-C / EOF）抛 `Cancelled`；会改动系统状态的流程包在
`Transaction` 内，`backup_file` / `track_path` / `add_undo` 登记回退；正常走完即 commit，中途
取消/异常按 LIFO 逆序回滚，单项失败不阻断其余。`Cancelled` 被事务吞掉并回退后平滑返回上层菜单。

---

## 7. 第三方资产

本项目不打包任何二进制/UI/geo 数据，全部运行时按需下载（见 `core.py`），各自保留原始许可证：
Mihomo 核心（MetaCubeX/mihomo, GPL-3.0）、Web 面板（MetaCubeX/metacubexd）、geo 数据
（MetaCubeX/meta-rules-dat）、订阅转换后端（公共 subconverter 实例）。本项目代码以 MIT 发布。
