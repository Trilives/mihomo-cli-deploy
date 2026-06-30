# mihomo CLI 部署系统 · 架构（重新移植蓝图）

交互式 CLI 部署 / 管理 **mihomo（Clash.Meta）** 的零依赖系统。一个入口 `mihomo.sh`，
全流程交互完成 **初始化 / 更改配置 / 网络测试 / 卸载**。

本文是**从姊妹项目 [sing-box CLI 部署系统](https://github.com/Trilives/singbox_cli_ui)
重新移植**的设计蓝图：复用同一套交互骨架（TUI / 事务回退 / 服务管理 / 自愈 / 定时器），
但**配置生成范式与 sing-box 版根本不同**——见 §1、§3。

> 本仓库已清空工作区（仅留 `.git`），按本蓝图重新落地代码。旧实现备份于
> `../mihomo-cli-deploy.backup-*.tar.gz`。

---

## 1. 与 sing-box 版的根本差异（设计原点）

mihomo 本身就是 Clash.Meta 内核，**原生消费机场的 Clash/mihomo 订阅**。因此本项目
**不做协议转换、不重建分流**，而是：

| 维度 | sing-box 版 | **mihomo 版（本项目）** |
| --- | --- | --- |
| 配置范式 | Clash 订阅 → **本地逐节点转换** → 自建 outbounds/route/dns（自己分流） | **直用机场订阅** YAML，**最小改写**必要字段，机场自带的 proxy-groups/rules/dns 全部保留 |
| 分流来源 | 项目内置（AI/流媒体/地区组/CN 直连…） | **机场订阅自带**为主；项目自定义分流降级为**可选叠加层**（默认关） |
| 配置文件 | `config.json`（sing-box JSON） | `config.yaml`（Clash/mihomo YAML） |
| 转换器 | `subscription/convert.py`（~760 行，核心） | **删除**。改为 `subscription/patch.py`（最小改写，~百行） |
| geo 数据 | 必下 `geosite-cn.srs` / `geoip-cn.srs` | **默认下载** `geoip.metadb` + `geosite.dat`：机场订阅的 rules 普遍内联 `GEOIP/GEOSITE`，缺 geo 数据会导致 `mihomo -t` 校验失败（已实测，见 §13） |
| 内核 | SagerNet/sing-box，`*.tar.gz` | MetaCubeX/mihomo，`*.gz` 单文件（解压方式不同） |
| 校验命令 | `sing-box check -c cfg.json` | `mihomo -t -f cfg.yaml` |

**一句话**：sing-box 版把「机场给的东西」拆开重组；mihomo 版**尽量原样用机场给的东西**，
只接管「部署/运行时」这一层（端口、外部控制器、UI、TUN、局域网、服务）。

---

## 2. 设计取向（继承自 sing-box 版）

| 决策 | 选择 | 理由 |
| --- | --- | --- |
| 语言 | Python 为主，`mihomo.sh` 仅瘦入口 | 模块化、可单独 `-m` 调用 |
| 运行时依赖 | **仅系统 `python3` 标准库** | 部署机常无代理，pip 装包慢/易失败 |
| YAML 解析 | 自带 `yamlmini`（替代 PyYAML） | 零依赖解析 Clash 订阅 |
| **配置输出** | **dict → `json.dumps` 写为 `config.yaml`** | **JSON 是合法 YAML 超集，mihomo 直接解析；省掉 YAML dumper**（见 §5） |
| 网络下载 | 外部 `curl` 子进程 | 稳定、沿用原脚本习惯 |
| 界面 | stdlib 自绘 TUI（termios + ANSI） | 零依赖；非 TTY 自动回退编号菜单 |
| 提权 | 按需 `sudo`（`shell.run_root`） | 普通用户启动，需 root 时自动提权 |

**硬约束（零依赖）**：不使用虚拟环境、不装任何 pip 包、不用 PyYAML。
**范围**：仅 Linux + systemd；单内核（mihomo）；单 active 订阅模型。

---

## 3. 三项已确认的关键决策

1. **配置策略 = 直用订阅 + 最小改写**。下载机场原生 Clash/mihomo 订阅，原样作为
   `config.yaml`，仅覆写部署必需字段：`mixed-port` / `allow-lan` / `external-controller`
   / `external-ui` / `secret` / `tun` / 必要的 `dns`。订阅自带的 `proxies` /
   `proxy-groups` / `rules` / `rule-providers` **全部保留不动**。
2. **base64 / 通用订阅 → subconverter 转 Clash**。机场没给 Clash 订阅时，经 subconverter
   后端把 base64 转成 Clash YAML，mihomo 再直接吃。保留自建后端选项。
3. **TUN 由本部署层控制**。无论订阅里有没有 `tun` 段，都由部署层按开关统一覆写
   （enable / stack / dns-hijack / 排除网段），保证行为可控、与 sing-box 版体验一致。

---

## 4. 目录结构

```
mihomo-cli-deploy/
├── mihomo.sh                   # 瘦入口：环境检查 → PYTHONPATH=lib exec python3 -m mihomo_deploy
├── ARCHITECTURE.md             # 本文
├── README.md
├── LICENSE                     # MIT
├── lib/mihomo_deploy/          # Python 主体（模块可单独 -m 调用）
│   ├── __main__.py             # 入口分发：init / modify / nettest / uninstall / update
│   ├── paths.py                # 统一路径常量（mihomo / config.yaml / /etc/mihomo）
│   ├── shell.py                # 子进程 / 日志 / 彩色输出 / run_root 提权        ◎复用
│   ├── errors.py               # 共享异常（Cancelled / SaveExit）                ◎复用
│   ├── keys.py                 # 可中断终端输入                                  ◎复用
│   ├── menu.py                 # 自绘 TUI 组件                                   ◎复用
│   ├── tx.py                   # 事务 / 回退引擎                                 ◎复用
│   ├── yamlmini.py             # 极简 Clash YAML 解析器                          ◎复用
│   ├── flows/                  # 入口流程编排
│   │   ├── init.py             # 初始化全流程                                    ◐改写
│   │   ├── modify.py           # 更改配置全流程                                  ◐改写
│   │   ├── nettest.py          # 网络测试                                        ◎复用
│   │   ├── uninstall.py        # 卸载                                            ◐改写(名称/路径)
│   │   └── common.py           # 流程间共享交互                                  ◐改写
│   ├── core.py                 # 下载内核(mihomo) + Web UI(+按需 geo 数据)        ◐改写(内核源/解压)
│   ├── service.py              # systemd 注册到 /etc/mihomo，同步 config.yaml     ◐改写
│   ├── resilience.py           # 网络自愈（NM 钩子 + watchdog）                   ◎复用
│   ├── timer.py                # 每周自动更新定时器                              ◎复用
│   ├── node_select.py          # 交互切换/固定节点（Clash API + 实时测速）        ◎复用(mihomo 兼容)
│   ├── proxyenv.py             # TUN 关闭时写 shell 代理环境变量                  ◎复用
│   ├── firewall.py             # 局域网代理放行/撤销端口                          ◎复用
│   ├── customize.py            # 定制层：部署字段 + 可选分流叠加开关              ◐大幅简化
│   └── subscription/           # 订阅子系统
│       ├── manager.py          # 命名订阅 增/删/改名/切换/列表/刷新              ◐改写
│       ├── fetch.py            # 下载订阅原始内容                                ◎复用
│       ├── detect.py           # 来源识别（clash / base64；singbox 来源删除）    ◐改写
│       ├── b64.py              # base64 → subconverter → Clash YAML              ◐改写
│       ├── patch.py            # 【新增】Clash YAML → 最小改写为运行时 config    ★新增
│       └── overlay.py          # 【新增·可选】自定义分流叠加层                    ★新增(可选)
├── templates/                  # systemd unit / NM 钩子 / healthcheck 模板        ◐改写
├── tests/                      # yamlmini / patch / overlay 测试
└── state/                      # 运行期产物（.gitignore）
```

图例：◎直接复用（仅改名称常量）｜◐改写｜★新增｜（无标）= 框架不变。

`state/` 关键文件：`subscriptions/<name>/{meta.json,raw.<ext>,config.yaml}`、
`active`（当前生效订阅名）、`config.yaml`（生效配置）、`customize.json`（定制层）。

---

## 5. 配置生成：直用订阅 + 最小改写（`subscription/patch.py`）

**核心流程**（取代 sing-box 版的 `convert.py`）：

```
机场 Clash 订阅 YAML
      │  yamlmini.load → dict
      ▼
patch.apply(cfg_dict, customize)   # 仅改写部署必需字段，业务字段原样保留
      │
      ▼
json.dumps(dict) → state/config.yaml   # JSON 即合法 YAML，mihomo 直接解析
      │
      ▼
mihomo -t -f config.yaml  校验
```

**patch 只动这些字段（其余 100% 保留订阅原值）**：

- `mixed-port: 7890`（统一本地代理端口，nettest/proxyenv 依赖）
- `allow-lan`: 由 `lan_proxy` 决定（true→`0.0.0.0`，false→仅本机）
- `bind-address` / `external-controller`: 由 `lan_panel` 决定（`127.0.0.1:9090` 或 `0.0.0.0:9090`）
- `external-ui`: 指向 `state/ui`（部署时改写为 `/etc/mihomo/ui`）
- `secret`: 面板密钥（lan_panel 开启时强制要求）
- `tun`: **按 `enable_tun` 整段覆写**（见 §3.3）。开 → `{enable:true, stack:gvisor,
  auto-route:true, auto-detect-interface:true, dns-hijack:[...], route-exclude-address:[...]}`；
  关 → `{enable:false}`，纯代理模式（配合 proxyenv 写环境变量）。
- `dns`: 订阅有则**保留**；订阅没有 `dns` 段则注入一份可用的最小默认（mihomo 开 TUN 时
  需要 DNS），引导服务器取 `bootstrap_dns_server`。

**为什么用 JSON-as-YAML 输出**：mihomo 用 `gopkg.in/yaml.v3` 解析，YAML 是 JSON 的超集，
合法 JSON 一定是合法 YAML。这样只需 `yamlmini.load`（读）+ `json.dumps`（写），
**无需实现 YAML dumper**，零依赖约束下最省心（已实测通过，见 §13）。

> ⚠️ **`json.dumps` 必须带 `ensure_ascii=False`**：默认的 `\uXXXX` 转义会被 mihomo 的
> YAML 解析器拒绝（`invalid Unicode character escape code`）。中文节点名等必须以真实
> UTF-8 字符直出。`manager` / `service` 写盘处均已固定 `ensure_ascii=False`。

---

## 6. 订阅来源（来源类型收敛为两类）

| 来源 | 路径 | 隐私 |
| --- | --- | --- |
| **Clash / mihomo 订阅**（★推荐） | `raw(yaml) →` patch | 全程本地，凭证不外泄 |
| **通用 base64** | `raw(b64) →` subconverter(clash) `→` patch | 凭证发往后端，可换自建 |

> sing-box 版的「sing-box 直链」来源在本项目**删除**（mihomo 不吃 sing-box JSON）。
> 若机场只给 sing-box 配置，提示用户改用其 Clash 订阅。

subconverter 后端取 `customize.json.subconverter_backend`（默认 `https://sub.v1.mk`，
`&target=clash`）。检测逻辑 `detect.py`：YAML 且含 `proxies:` → clash；否则尝试 base64。

---

## 7. 自定义分流叠加层（可选 · `subscription/overlay.py`）

**默认关闭**。开启后在订阅 config 之上**叠加**项目自定义分流（不替换订阅原规则）：

- 在 `proxy-groups` 头部插入 `AI` / `Streaming` 选择组（引用订阅中已存在的出站组/节点）；
- 在 `rules` 头部插入 AI 域名、流媒体域名、直连域名规则（命中走对应组）；
- 可选地区分组（SG / HK）：按关键词从订阅节点筛出 `url-test` 组。

叠加层需要解析订阅里**可引用的组名/节点名**，复杂度高于 patch，故独立成模块、
独立开关、默认关。字段沿用 `customize.json` 中 `ai_domain_suffixes` 等（默认值保留，
仅在叠加开启时生效）。

---

## 8. 定制层 `state/customize.json`（简化）

字段分两组：**部署字段（始终生效）** 与 **分流叠加字段（仅叠加开启时生效）**。

**部署字段**（核心）：
- 开关：`enable_tun` / `lan_proxy` / `lan_panel`
- 标量：`bootstrap_dns_server` / `bootstrap_dns_port` / `subconverter_backend`
  / `github_mirror` / `download_proxy` / `secret`
- 列表：`tun_route_exclude_cidrs`（TUN 排除网段）/ `tun_exclude_uids`

**分流叠加字段**（默认不生效，`enable_overlay=false`）：
- 开关：`enable_overlay` / `generate_sg_groups` / `generate_hk_groups`
- 列表：`ai_domain_suffixes` / `streaming_domain_suffixes` / `direct_domain_suffixes`
  / `prefer_keywords`(SG) / `hk_prefer_keywords`(HK)

编辑器沿用 sing-box 版的**缓冲式滑动菜单**：`esc` 保存退出才写盘，`^R` 放弃；
常用部署字段前置，叠加字段在「自定义分流叠加」子菜单内。

---

## 9. 内核 / UI / 资源下载（`core.py` 改写点）

| 组件 | sing-box 版 | mihomo 版 |
| --- | --- | --- |
| 内核仓库 | `SagerNet/sing-box` | `MetaCubeX/mihomo` |
| 内核资产 | `sing-box-*-linux-<arch>.tar.gz`（tar 解压） | `mihomo-linux-<arch>-vX.Y.Z.gz`（**gzip 单文件**解压）；`compatible` 变体兜底旧 CPU |
| 校验 | `sing-box check` | `mihomo -t -f` |
| Web UI | metacubexd | metacubexd（**不变**，Clash API 面板通用） |
| geo 数据 | 必下 `*.srs` | **默认下载** `geoip.metadb` + `geosite.dat`（订阅 rules 内联 GEOIP/GEOSITE，缺则校验失败）。源：`MetaCubeX/meta-rules-dat` 的 `latest` 滚动发布 |

`_ARCH_MAP`、curl 代理优先→直连兜底通道、缓存校验、GitHub 镜像前缀逻辑**复用**。
仅需把「tar.gz 解压取 `sing-box`」改为「gz 解压取 `mihomo` 单文件」。

---

## 10. systemd 服务（`service.py` 改写点）

- 运行时目录 `/etc/sing-box` → `/etc/mihomo`；服务名 `sing-box` → `mihomo`
  （冲突名互换为 `sing-box`）。
- 暂存配置 `<name>.json` → `<name>.yaml`；路径改写：`external-ui` → `/etc/mihomo/ui`；
  overlay 用到的 rule-provider 本地路径 → `/etc/mihomo/ruleset/`。
- mihomo 无 sing-box 的 `experimental.cache_file`，改用 mihomo 的
  `profile: {store-selected: true}` 持久化选组（写在 patch 默认里）。
- 校验 `sing-box check -c` → `mihomo -t -f`。
- unit 模板 `mihomo.service.tmpl`：`ExecStart=/etc/mihomo/mihomo -d /etc/mihomo -f
  /etc/mihomo/config.yaml`，`CAP_NET_ADMIN` 等能力沿用（TUN 需要）。

---

## 11. 复用模块（仅改名称常量）

- **node_select.py**（◐**实为重写**）：Clash API endpoints（`/proxies`、`/proxies/<n>/delay`、
  `/version`）mihomo 完全兼容，但**配置结构需适配**——按 `proxy-groups`（`name`/`type:select`/
  `proxies`）而非 sing-box 的 `outbounds`，控制器从顶层 `external-controller` 读。已重写并实测。
- **nettest.py**：经本地 `127.0.0.1:7890`（mixed-port）测 TTFB + 出口 IP，与内核无关，复用。
- **resilience.py / timer.py / proxyenv.py / firewall.py**：与内核解耦，改路径/服务名即可。
- **menu.py / keys.py / tx.py / shell.py / errors.py / yamlmini.py**：交互/事务/工具层，原样复用。

---

## 12. 可中断与回退（ESC + 事务，复用）

任意交互处 `ESC`/`Ctrl-C`/`EOF` 抛 `Cancelled`；改动系统状态的流程包在 `Transaction`，
`backup_file` / `track_path` / `add_undo` 登记回退，正常走完 commit，中途按 LIFO 回滚，
单项失败不阻断其余。「更改配置」整个会话是一个事务：`esc`=保存提交，`^R`=回退并退出。

---

## 13. 实测结论（基于 mihomo v1.19.27 + 真实机场订阅）

1. **JSON-as-YAML 输出**（§5）✅ **已验证**：`json.dumps` 写出的 `config.yaml`（纯 JSON
   内容）经 `mihomo -t` 校验通过（`test is successful`）。**确定不实现 YAML dumper**。
2. **mihomo 内核资产命名** ✅ **已验证**：`mihomo-linux-<arch>-<tag>.gz`（gzip 单文件）；
   `-compatible-` 为老 CPU 兜底；amd64 另有 `-v1/v2/v3-`、`-go120/go123-` 变体。
   默认选标准包，`--compatible` 选兜底包。gzip 单文件解压可用。
3. **geo 数据必需** ✅ **已验证**：完整真实订阅（4232 rules，含 `GEOIP,CN`）在**无 geo
   数据**时 `mihomo -t` 报 `can't download MMDB` 失败；放入 `geoip.metadb` + `geosite.dat`
   后校验通过。故 geo 数据**默认下载**（修正 §1/§9）。
4. **TUN 默认 stack**：默认 `gvisor`，定制层 `tun_stack` 可改 `system`/`mixed`。
5. **订阅无 `dns` 段时**注入 fake-ip 默认（`patch._default_dns`）；真实订阅多自带 dns，保留。
6. **overlay 引用组名**（待做）：自定义分流叠加要引用订阅已有组，命名因机场而异，需健壮兜底。

---

## 14. 移植工作分解（✅ 全部完成并实测）

> 状态：1–9 步均已落地。核心管线「订阅 → patch → config.yaml → `mihomo -t` 校验 →
> 服务布局」已用 mihomo v1.19.27 + 真实机场订阅端到端验证；patch / overlay 单元测试全绿。
> 唯一未在本机执行的是真正的 systemd 注册/启动（避免影响现网 sing-box 服务）。

实施顺序：

1. **骨架落地**：复制 `shell/errors/keys/menu/tx/yamlmini/paths` 并改名 `mihomo_deploy`。
2. **patch.py + 输出管线**：先打通「Clash 订阅 → patch → config.yaml → mihomo -t」。
3. **core.py**：mihomo 内核下载/解压；UI 复用。
4. **service.py + 模板**：注册 `/etc/mihomo` 服务并跑通。
5. **subscription/manager + fetch + detect + b64**：订阅增删改切与 base64 兜底。
6. **flows/init + modify + uninstall + common**：串起全流程交互。
7. **复用 node_select / nettest / resilience / timer / proxyenv / firewall**：改常量接入。
8. **customize.py 简化** + **overlay.py（可选叠加）**：最后做高级分流。
9. **tests + README**。

---

## 15. 第三方资产

运行时按需下载，各自保留原始许可证：mihomo 内核（MetaCubeX/mihomo, GPL-3.0）、
Web 面板（MetaCubeX/metacubexd）、geo 数据（MetaCubeX/meta-rules-dat，仅 overlay 用）、
订阅转换后端（公共 subconverter 实例）。本项目代码以 MIT 发布。
