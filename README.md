# mihomo CLI 部署系统

在 Linux 上交互式部署 / 管理 **mihomo（Clash.Meta）** 的命令行系统。一个入口
`./mihomo.sh`，全流程交互完成：**初始化 / 更改配置 / 暂停启动 / 网络测试 / 卸载**。

- **直用机场订阅**：mihomo 原生吃 Clash 配置，本系统**直接消费机场的 Clash/mihomo
  订阅**，只最小改写部署必需字段（端口 / 局域网 / 外部控制器 / TUN / 面板），机场自带的
  策略组与分流规则**全部保留**。自定义分流为**可选叠加**，默认不启用。
- **零第三方依赖**：只用系统自带 `python3` 标准库，不装 pip 包、不用虚拟环境。
  Clash YAML 用内置 `yamlmini` 解析；配置以 JSON 写出（合法 YAML，mihomo 直接解析）。
- **自绘 TUI**：方向键导航、反显高亮；非 TTY 自动回退编号菜单。
- **随时可中止可回退**：任意步骤按 **ESC** 取消，已应用的改动自动回滚。
- **按需提权**：普通用户启动，需要 root 时自动 `sudo`。

架构与设计细节见 [ARCHITECTURE.md](ARCHITECTURE.md)。

> 想用 **sing-box**？见姊妹项目
> [singbox_cli_ui](https://github.com/Trilives/singbox_cli_ui)：同一套交互骨架的 sing-box 版。

## 快速开始

```bash
chmod +x mihomo.sh
./mihomo.sh
```

进入主菜单选「初始化」，按提示完成（多数项**直接回车**即用推荐默认）：

1. 填下载代理（留空=直连；用于加速下载内核 / UI / geo 数据）。
2. 选 **TUN 模式**（默认开=整机透明代理；关=纯代理，可选写入 `~/.bashrc` 代理变量）。
3. （可选）开启局域网代理，按需放行防火墙 7890。
4. 下载 mihomo 内核 + geo 数据（geoip.metadb / geosite.dat）；**Web 面板（metacubexd）
   可选下载**。选择下载后可再启用**「根路径直接打开」**（见下文 Web 面板）。
5. 添加首个订阅：**链接留空=暂不配置、直接结束**；询问是否叠加自定义分流（默认否＝
   直接沿用机场自带分流）。
6. 注册 systemd 服务，（可选）独立 Web 面板、网络自愈、每周更新。

> 装好后主菜单的**「启动 / 暂停服务」**可一键统一启停 mihomo 及全部伴生服务（见下文）。

## 订阅来源（二选一）

| 来源 | 说明 |
| --- | --- |
| **Clash / mihomo 订阅**（★推荐） | 直接消费，最小改写，凭证不外泄、兼容性最好 |
| **通用 base64 订阅** | 经云端 subconverter 转为 Clash 再最小改写 |

> 机场常提供「Clash」或「Clash.Meta / mihomo」订阅链接，优先用它。
> base64 走第三方 subconverter 会发送节点凭证；默认后端 `https://sub.v1.mk`，
> 隐私敏感者可在「定制层」改为自建后端。

## 最小改写做了什么

下载的机场订阅 YAML 原样作为配置，仅覆写：`mixed-port`(统一 7890) / `allow-lan` /
`external-controller` / `external-ui` / `secret` / `tun`（按开关整段覆写）/ 缺失时补 `dns`。
订阅自带的 `proxies` / `proxy-groups` / `rules` / `rule-providers` **全部保留**。

## 地区自动测速聚合组（可选增强）

机场订阅通常已自带按地区分的 select 组（HK / SG / JP…，但需手动逐个挑节点）。在「编辑定制
层」开启 **`enable_region_groups`**（再勾选新加坡 / 香港），即会**额外**生成 `SG-Auto` /
`HK-Auto` 这类 **url-test 聚合组**：按节点名关键词聚合该地区节点、自动选最低延迟，并插入
主选择组前部，**可直接作为出口选用**——无需自己建分组。

- 本功能**独立开关**，不依赖下文的自定义分流叠加；关键词在定制层「新加坡 / 香港关键词」可调。
- 改完定制层会提示「用本地原文重新生成生效订阅并重启」，聚合组即刻生效。

## 自定义分流叠加（可选）

「编辑定制层」开启 `enable_overlay` 后，在机场分流之上**叠加**：AI / 流媒体选择组、对应
域名规则（插到规则最前，优先命中）；如同时开了地区聚合组，AI / 流媒体组会一并纳入它们作为
成员。默认关闭。

## 定制层

「更改配置 → 编辑定制层」交互式增删改，缓冲式（`esc` 保存退出才写盘，`^R` 放弃）：

- **部署字段（始终生效）**：TUN 开关 / 协议栈、局域网代理、LAN 面板、面板密钥、
  引导 DNS、subconverter 后端、GitHub 加速、下载代理、TUN 排除网段 / UID。
- **叠加字段（仅 `enable_overlay` 时生效）**：AI / 流媒体 / 直连域名后缀、地区组关键词。

## 节点切换

「切换 / 固定节点」：从订阅的主选择组（如 Proxies / 节点选择）按地区/子组浏览节点，
经 Clash API 实时测速与热切换，并把选中项固定为组首成员（跨重启持久）。

## 网络测试

「网络测试」：经本地 `127.0.0.1:7890` 并发测一批目标的 TTFB，并对多方向探测出口 IP /
落地（流媒体 / 常用站点 / AI 服务）。

## 命令行（非交互，便于脚本 / 定时器）

```bash
./mihomo.sh init        # 初始化
./mihomo.sh modify      # 更改配置
./mihomo.sh nettest     # 网络测试
./mihomo.sh pause       # 暂停主服务 + 全部伴生单元（watchdog / 定时器）
./mihomo.sh resume      # 启动主服务 + 全部伴生单元
./mihomo.sh uninstall   # 卸载
./mihomo.sh update      # 更新内核/UI/geo 并同步重启（每周定时器调用）

# 单模块调用
python3 -m mihomo_deploy.core --only core --force
python3 -m mihomo_deploy.service status -n mihomo
python3 -m mihomo_deploy.service pause          # 统一暂停 mihomo + 全部伴生单元
python3 -m mihomo_deploy.webui install --port 9091   # 独立根路径面板
```

## Web 面板

面板（metacubexd）在初始化时**可选下载**（不需要可跳过，省下载、保持精简）。

**两种打开方式：**

| 方式 | 地址 | 说明 |
| --- | --- | --- |
| mihomo 内置路径 | `http://127.0.0.1:9090/ui/` | mihomo 把面板挂在控制器的 `/ui` 子路径，**须带 `/ui/` 后缀**（这是 mihomo 与 sing-box 的固有差异） |
| **独立面板（根路径直开）** | `http://127.0.0.1:9091/` | 可选增强：把同一份面板托管在独立端口的**根路径**，浏览器开根地址即用，体验同 sing-box |

**根路径直开**由独立 systemd 服务 `mihomo-webui.service` 提供（`python3 -m http.server`
托管面板，`config.js` 的 `defaultBackendURL` 指向控制器 9090；依赖 Clash API 默认开启的
CORS 跨端口通信）。在初始化时可一键启用，或之后在「更改配置 → 独立 Web 面板」管理 / 换端口。

> 为什么不直接换端口就能根路径打开？因为 mihomo 把控制器 API 占在根 `/`、面板固定挂在 `/ui`
> 子路径，换端口也改不了路径前缀；故用独立静态服务在根路径另起一份。

远程查看（未开 LAN 面板时）用 SSH 端口转发：

```bash
ssh -N -L 9090:127.0.0.1:9090 -L 9091:127.0.0.1:9091 user@server
```

确需开放局域网时在「定制层」开启 `lan_panel`（务必设 `secret` + 防火墙；独立面板会随之绑到
`0.0.0.0` 并提示放行其端口）。

## 服务启停（统一控制）

主菜单第③项**「暂停服务 ⏸ / 启动服务 ▶」**一键统一启停，标签随主服务当前状态变化：

- **暂停**：停止 mihomo 主服务 + **全部伴生单元**（网络自愈 watchdog、独立 Web 面板、
  每周更新定时器）。先停伴生再停主服务，避免 watchdog 在主服务停掉前抢先把它重启。
  暂停为运行时停止，单元仍保持开机自启——**重启系统后会自动恢复运行**。
- **启动**：启动主服务，再拉起全部已安装的伴生单元。

> 伴生单元（尤其 watchdog）必须与 mihomo 统一控制，否则单独停 mihomo 会被它探测到不通而重新
> 拉起。命令行：`./mihomo.sh pause` / `./mihomo.sh resume`
> （或 `python3 -m mihomo_deploy.service pause|resume`）。

## 目录结构

```
mihomo-cli-deploy/
├── mihomo.sh               # 瘦入口：环境检查 → 调起 Python CLI
├── lib/mihomo_deploy/      # Python 主体（零依赖，模块可单独 -m 调用）
├── templates/              # systemd unit / NM 钩子 / healthcheck 模板
├── tests/                  # yamlmini / patch / overlay / regiongroups 测试
└── state/                  # 运行期产物（gitignore：内核/UI/geo/订阅/配置）
```

## 测试

```bash
python3 tests/test_yamlmini.py      # YAML 解析对拍 PyYAML（需 PyYAML，仅测试用）
python3 tests/test_patch.py         # 最小改写逻辑
python3 tests/test_overlay.py       # 自定义分流叠加
python3 tests/test_regiongroups.py  # 地区自动测速聚合组
```

## 环境要求

Linux + systemd；系统自带 `python3`（≥3.8）、`curl`。TUN / 服务需 root（自动 sudo）。

## 第三方资产与致谢

本项目**不打包任何二进制 / UI / geo 数据**，全部在运行时从上游按需下载（见 `core.py`），
各自保留其原始许可证：

| 资产 | 来源 | 用途 |
| --- | --- | --- |
| mihomo 内核 | [MetaCubeX/mihomo](https://github.com/MetaCubeX/mihomo)（GPL-3.0） | 代理核心 |
| Web 面板 | [MetaCubeX/metacubexd](https://github.com/MetaCubeX/metacubexd) | Clash API 面板 |
| geo 数据 | [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat) | geoip.metadb / geosite.dat |
| 订阅转换后端 | 公共 [subconverter](https://github.com/asdlokj1qpi23/subconverter) 实例（默认 `sub.v1.mk`） | base64 来源解析 |

## 许可证

本项目代码以 [MIT](LICENSE) 许可证发布。上述第三方资产不随本仓库分发，使用时受其各自许可证约束。
