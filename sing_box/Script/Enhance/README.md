# sing-box Enhance 脚本

本目录放 sing-box 配置增强 / 转换脚本：

- `clash_nodes_to_singbox.py`：从 Clash/Mihomo 的 `config.yaml` 提取节点，生成可直接校验的 sing-box TUN 配置（`config.json`）。
- `select_singbox_node.py`：交互式切换 / 固定代理分组的首选节点，保证重启服务时节点不变。
- `clash_nodes_to_singbox_config.json`：转换脚本的本地自定义配置（DNS、路由、直连进程、TUN UID 排除等）。含私有信息（EasyTier relay 域名、UID），已被 `.gitignore` 忽略。
- `clash_nodes_to_singbox_config.json.example`：脱敏样本，首次使用时复制。

---

## clash_nodes_to_singbox.py · 本地兜底转换

### 基本用法

首次使用先从样本复制本地配置，再按需修改（如 `direct_domain_suffixes` 的 EasyTier relay 域名、`tun_exclude_uids` 的真实 UID）：

```bash
cp ./sing_box/Script/Enhance/clash_nodes_to_singbox_config.json.example \
   ./sing_box/Script/Enhance/clash_nodes_to_singbox_config.json
```

然后运行（默认路径开箱即用）：

```bash
./sing_box/Script/Enhance/clash_nodes_to_singbox.py
```

默认输入 `./config.yaml`，输出 `./sing_box/config.json`，自定义配置 `./sing_box/Script/Enhance/clash_nodes_to_singbox_config.json`，CN 规则集 `./sing_box/ruleset/{geosite,geoip}-cn.srs`。也可显式指定：

```bash
./sing_box/Script/Enhance/clash_nodes_to_singbox.py ./config.yaml ./sing_box/config.json \
  --prefer 'Singapore,SG,新加坡,狮城' --hk-prefer 'Hong Kong,HongKong,HK,香港' --default-outbound Proxy
./sing_box/Script/Enhance/clash_nodes_to_singbox.py --custom-config /path/to/config.json
./sing_box/Script/Enhance/clash_nodes_to_singbox.py --strict   # 遇不支持/字段不全的节点直接失败
```

当前支持从 `proxies` 转换 `anytls`、`trojan`、`ss`/`shadowsocks`、`vmess`、`vless`、`hysteria2`/`hy2`、`tuic`、`socks`/`socks5`、`http`。会生成 `tun` + `mixed` 入站、基础 DNS、基础分流和 Clash API。Shadowsocks `obfs` 节点转为 `obfs-local` 插件配置，运行环境需装 `obfs-local`。

### 自定义配置字段

`clash_nodes_to_singbox_config.json` 支持：

- `ai_domain_suffixes` / `streaming_domain_suffixes`：分别走 `AI` / `Streaming` 出站的域名后缀。
- `direct_domain_suffixes`：直连域名后缀。非空时新增一个 `Direct` 组（默认 `DIRECT`，可在面板切到 `Proxy`/`Auto`），命中域名优先路由到它并走本地 DNS 解析。
- `local_bypass_domains`：本地直连域名。
- `route_exclude_ip_cidrs`：TUN 自动路由排除网段，并生成直连路由规则。
- `bypass_process_names`：直连进程名（如 `tailscaled`）。
- `tun_exclude_uids`：写入 TUN 入站 `exclude_uid`，让指定系统用户流量绕过 sing-box。
- `lan_panel`：`true` 监听 `0.0.0.0:9090` 并放行私有网络；`false`（默认）仅 `127.0.0.1:9090`。命令行 `--lan-panel` 可强制开启。
- `bootstrap_dns_server` / `bootstrap_dns_port`：引导 DNS（`dns-direct`）地址与端口。默认 `223.5.5.5:53`，开箱即用；需跟随系统/路由器 DNS 时填 `"dhcp"`。

### 出站分组

- `Proxy`：主选择器，内部分组优先，便于常规切换。过滤订阅说明伪节点（`Traffic:`、`Expire:`、`剩余流量`、`过期时间` 等）。
- `Auto`：全节点 `urltest`，同样过滤伪节点。
- `SG-Auto` / `SG-Fallback`：按 `--prefer` 关键词从首选新加坡节点生成的自动测速组 / 手动选择组；名称含 `实验` 的节点不进这两个组，但仍留在 `Auto` 和 `Proxy`。
- `HK-Auto` / `HK-Fallback`：按 `--hk-prefer` 关键词从首选香港节点生成的自动测速组 / 手动选择组，规则与新加坡组一致（同样排除名称含 `实验` 的节点）。
- `AI` / `Streaming`：分别匹配 `ai_domain_suffixes` / `streaming_domain_suffixes`，默认选 `Proxy`，也可切到 `SG-Auto`/`SG-Fallback`/`HK-Auto`/`HK-Fallback`/`Auto`/`DIRECT`。
- `Direct`：可选特殊直连组，仅 `direct_domain_suffixes` 非空时生成，优先级高于 `AI`/`Streaming`/CN 分流。

> **地区组开关**：脚本顶部 `GENERATE_SG_GROUPS` / `GENERATE_HK_GROUPS` 两个常量分别控制新加坡、香港地区组（默认均为 `True`）。设为 `False` 后不再生成对应的 `*-Auto`/`*-Fallback` 组，`AI`/`Streaming`/`Proxy` 选择器也会自动省略它们；即便开着，若没有匹配 `--prefer`/`--hk-prefer` 的节点也不会生成。

顶层 `outbounds` 先放真实节点和常用策略组，再放 `SG-Auto`/`SG-Fallback`/`HK-Auto`/`HK-Fallback`/`Auto` 等自动/地区分组，`Fallback` 放最后。`Proxy` 默认依次优先 `SG-Auto` → `HK-Auto` → `Auto`。TUN 自动路由排除 `127.0.0.0/8`、`0.0.0.0/8`、`::1/128`，并强制 `localhost` 与本机地址走 `DIRECT`。

### 校验

```bash
./sing_box/sing-box check -c ./sing_box/config.json   # 本地无该二进制时改用系统的 sing-box
```

---

## 交互式切换 / 固定节点

`select_singbox_node.py` 本质是把选中项设为代理分组（默认 `Proxy`）的**第一个成员**并对齐 `default`。sing-box selector 在无持久化选择时取第一个成员，而 `default` 优先级更高——两者都设成选中节点，重启后才稳定停在该项，不会被 `SG-Auto` 这类 `urltest` 自动测速组乱切。

```bash
./sing_box/Script/Enhance/select_singbox_node.py                    # 默认读 sing_box/config.json
./sing_box/Script/Enhance/select_singbox_node.py path/to/config.json
```

三步终端交互：

1. **选地区 / 分组**：列出有节点的主要地区（🇭🇰 香港 / 🇹🇼 台湾 / 🇯🇵 日本 / 🇰🇷 韩国 / 🇸🇬 新加坡 / 🇺🇸 美国），其余归「🌐 其他地区」；最后一项「🧭 分组」用于选 `SG-Auto`/`SG-Fallback`/`HK-Auto`/`HK-Fallback`/`Auto` 等子分组。
2. **选具体节点 / 分组**（`b` 返回上一步，`q` 退出）。
3. **是否重启**：选 `y` 则以 `sudo` 运行 `Script/setup_sing_box_service.sh`（终端提示输入密码）。

行为要点：

- 写配置后，若服务在跑则同时通过 Clash API 实时切换（地址/密钥读自 `experimental.clash_api`，`0.0.0.0` 自动按 `127.0.0.1` 访问）；服务未跑则跳过，重启后由配置生效。
- 仅依赖 Python3 标准库；自动探测主分组（优先 `Proxy`，否则成员最多的 selector）。
- 环境变量：`SINGBOX_GROUP` 强制指定分组；`RESTART_ARGS` 透传给重启脚本（如 `-n sing-box-main`）。

> 重新跑 `clash_nodes_to_singbox.py` 会重置成员顺序与 `default`，需要时再跑一次本脚本即可。

---

## CN 规则集

转换脚本不再用手写域名后缀做国内分流，而是生成 sing-box 官方推荐的 `rule_set`：

- `geosite-cn`：国内域名 DNS 本地解析 + 路由直连。
- `geoip-cn`：国内 IP 路由直连。

`.srs` 文件由 `./sing_box/Script/update_sing_box_core.sh` 下载自 SagerNet 官方仓库（`sing-geosite`、`sing-geoip`）。

## 每周自动更新

本仓库用本地 `rule_set`（`type: local`，启动时一次性读入），需定期更新 `.srs` 并重启服务才能保鲜。`sing_box/Script/` 下：

- `update_and_redeploy.sh`：依次跑 `update_sing_box_core.sh`（内核、Web UI、`geosite-cn.srs`/`geoip-cn.srs`）和 `setup_sing_box_service.sh`（重装 config 并重启）。额外参数透传给前者，如 `--libc musl`。
- `setup_weekly_update_timer.sh`：安装 systemd timer，默认每周一 03:00 跑 `update_and_redeploy.sh`。

```bash
sudo ./sing_box/Script/setup_weekly_update_timer.sh             # 安装（需 root）
sudo systemctl start sing-box-update.service                   # 立即手动跑一次
journalctl -u sing-box-update.service -f                       # 跟踪日志
systemctl list-timers sing-box-update.timer                    # 看下次执行
sudo ./sing_box/Script/setup_weekly_update_timer.sh --remove   # 卸载
```

timer 特性：`OnCalendar=Mon *-*-* 03:00:00`（`--on-calendar` 可改）、`Persistent=true`（关机错过开机补跑）、`RandomizedDelaySec=30min`（错峰避 GitHub 高峰，`--delay` 可调）、`After=network-online.target`。

> 该流程只更新内核/UI/规则集，**不重新生成 `config.json`**（节点不变）；订阅节点变化仍需手动跑 `clash_nodes_to_singbox.py`。服务若用 `-n <自定义名>` 安装，需相应调整。

---

## 深入：DNS bootstrap 与节点域名解析

**2026-06-09 故障**：进程没崩、自动更新也成功，但内外访问都异常，日志大量 `lookup ...: context deadline exceeded`。根因是代理节点 `server` 用域名，而 DNS 的 `remote` 路径又经 `AI`/`Proxy` 出站——出站还没解析出节点域名时，DNS 请求反过来依赖该出站，形成 bootstrap 闭环。

按 sing-box 1.12+ 的 `domain_resolver` 迁移，生成器在 `route.default_domain_resolver` 统一指定独立 bootstrap resolver，让所有出站的 `server` 域名（及 `DIRECT` 的直连域名）先用它解析：

```json
"default_domain_resolver": { "server": "dns-direct", "strategy": "prefer_ipv4" }
```

每个 DNS server 显式写 `detour`，让路径由配置表达，而非靠 TUN 额外排除公共 DNS IP：`dns-direct`(`223.5.5.5`)→`DIRECT`、`dns-dnspod`(`119.29.29.29`)→`DIRECT`、`dns-proxy`(DoH `1.1.1.1`)→`Proxy`。`detour` 值必须匹配现有出站 tag（当前直连出站 `DIRECT`、选择器 `Proxy`）。要跟随 DHCP DNS 时设 `bootstrap_dns_server: "dhcp"`。

注意两点：

- sing-box 不允许 DNS `detour` 到完全空的 direct 出站（报 `detour to an empty direct outbound makes no sense`），故生成器给 `DIRECT` 出站补同一个 bootstrap resolver。
- `prefer_ipv4`：优先 IPv4，避免无稳定 IPv6 出口时直连域名解析到 AAAA 报 `network is unreachable`，同时保留 IPv6 回退。

官方参考：[dial](https://sing-box.sagernet.org/configuration/shared/dial/) · [route](https://sing-box.sagernet.org/configuration/route/) · [dhcp server](https://sing-box.sagernet.org/configuration/dns/server/dhcp/) · [migration](https://sing-box.sagernet.org/migration/)

## 深入：EasyTier 绕过

EasyTier 的 P2P peer IP 动态发现，不应靠手工 IP 列表维护。推荐：

- 让 EasyTier 用独立系统用户运行（如 `easytier`）。
- 加高于 sing-box `9000+` 规则的策略路由，如 `ip rule add pref 1000 uidrange 997-997 lookup main`。
- 在 `clash_nodes_to_singbox_config.json` 设 `tun_exclude_uids`，让 sing-box TUN 也显式排除该 UID（取真实 UID，如 `id easytier` 得到的 `997`）。

这样保留 sing-box `strict_route`，同时让 EasyTier 动态 P2P 数据面稳定走物理网卡。

**但 UID 绕过只覆盖数据面，不覆盖 DNS 解析（2026-06-24 故障）**：节点失效时 EasyTier 跟着断，只有停 sing-box 才恢复。根因是 peer **域名的 DNS 解析**没被 UID 规则绕过：EasyTier 解析域名走 `getaddrinfo`→systemd-resolved，而 systemd-resolved 跑在另一个 UID，把全机 DNS 转进 sing-box；该域名未命中 DNS 规则时落到 `final`→`dns-proxy`(经 `Proxy`)，节点一失效解析就超时。这也是更广的脆弱点：节点失效时整机所有“未命中规则的域名”都会解析失败。

**修法**：把 EasyTier 的 peer/relay 域名加入 `direct_domain_suffixes`，让它走 `dns-direct`（`223.5.5.5` 经 `DIRECT`），解析与节点死活脱钩：

```json
"direct_domain_suffixes": ["dashscope.aliyuncs.com", "225284.xyz"]
```

relay 是固定 bootstrap 入口、非动态 peer，单列不违反“不维护动态 peer IP”原则。更彻底可在 `/etc/hosts` 钉死该域名，或在 EasyTier 配置直接写 relay IP。

---

## 注意事项

- 不要提交含订阅地址、节点密码、token 的生成配置；问题报告里也别直接粘贴。
- 改 TUN/DNS/路由字段后先 `sing-box check` 再启动。
- `route_exclude_ip_cidrs` 不要盲目加 `172.16.0.0/12`：当前 TUN DNS 地址在 `172.19.0.2` 网段。
- EasyTier 不再依赖域名/IP 列表绕过；`tailscale`/`tailscaled` 等 `bypass_process_names` 进程仍直连。
