# 项目交接说明（给新接手的人或 AI）

更新于 2026-10-29。读完本文就能知道：机器人跑在哪、代码在哪、有哪些记录、做过哪些决定、下一步是什么。

**密钥、密码、Token 一律不写在这里。** 下文只写它们放在哪里，要用时由用户本人在终端里操作。
服务器地址等私人信息用 `<服务器IP>` 这类占位符代替；真实值只在项目负责人本机的 `reports/PRIVATE_NOTES.local.md` 里，不上传。

---

## 1. 一句话概括

- 用户在一台 云服务商 云服务器上，跑着两个**模拟盘**（dry-run，不动真钱）的加密货币现货交易机器人，交易所是 Binance：
  - **X7Safe**：NostalgiaForInfinity X7 加上自写的安全层，模拟资金 10000 USDT；
  - **Combined_V3**：另一套独立的策略，模拟资金 1000 USDT。
- 本机（Windows，`D:\NostalgiaForInfinity`）只用来写代码、跑回测、写报告，**本机不跑机器人**。
- 目前的原则：**策略规则冻结，不改**，先积累模拟盘数据；**不上实盘**。

## 2. 用户偏好与规矩（必须遵守）

| 规矩 | 说明 |
|---|---|
| 语言 | 用**中文**回答，用简单、不带术语的话 |
| 磁盘 | 文件和缓存放 **D 盘**，C 盘空间不够 |
| 提交 | **用户说了才 commit 和 push**；公开前必须去掉私人信息 |
| 改服务器 | 先备份，记入 `reports/DEPLOY_LOG.md`，只在空仓时重启；要经用户同意 |
| 实验方法 | **先预注册**（开跑前写好假设、实验臂、采纳标准），结果出来后不改标准 |
| 密钥 | Telegram Token、交易所 API key 不要发给 AI；用户自己写到服务器上 |
| 系统设置 | Windows 系统设置（例如页面文件）由用户自己改 |
| 本机内存 | 一次只跑**一个** 18 个月回测，并开 `FT_LOWMEM=1`；空闲内存要 ≥ 19 GB |

## 3. 云服务器

| 项 | 值 |
|---|---|
| 服务商 | 云服务商 |
| 公网 IP | `<服务器IP>` |
| 登录 | `ssh root@<服务器IP>`，只能用密钥登录，密码登录已禁用；本机私钥在 `<本机 SSH 私钥>` |
| 防火墙 | ufw 只开 SSH；机器人 API 只监听 `127.0.0.1` |
| 费用 | 账户余额大约用到 **2027-01 中下旬**，之后按账户设置扣款。曾考虑换 其他服务商，还没决定 |
| 内存 | 很紧（Telegram 报告里会显示剩余量，约 700 MB） |

### 3.1 X7Safe（systemd 服务）

| 项 | 位置 |
|---|---|
| 服务名 | `nfi-dryrun.service`（模板见仓库 `scripts/deploy/nfi-dryrun.service`） |
| 根目录 | `/opt/nfi/`，运行用户 `nfi` |
| 运行中的策略 | `/opt/nfi/user_data/strategies/NostalgiaForInfinityX7Safe.py`，sha256 以 `5cd599…` 开头 |
| 策略备份 | 同目录下的 `.bak-20260930052733`、`.bak-20261017120411`、`.bak-20261018154834`、`.bak-20261018164737` |
| 配置 | `/opt/nfi/configs/`（`local-overrides-dryrun.json` 里有 `api_server` 的设置） |
| 交易数据库 | `/opt/nfi/user_data/tradesv3.dryrun.sqlite` |
| 日志 | `/opt/nfi/user_data/logs/dryrun.log`，也可以用 `journalctl -u nfi-dryrun` 看 |
| API | `127.0.0.1:8082` |
| 每周重启 | `nfi-dryrun-restart.timer`，周日 03:17 UTC，有持仓时跳过；重启脚本 `/opt/nfi/scripts/nfi_safe_restart.py` |
| 改动记录 | `/opt/nfi/DEPLOY_LOG.md`（和仓库 `reports/DEPLOY_LOG.md` 同一份） |

### 3.2 Combined_V3（Docker 容器）

| 项 | 位置 |
|---|---|
| 容器名 | `combined_v3_dryrun`（重启策略 unless-stopped） |
| 目录 | `/home/root/combined-v2-dryrun/`（目录名里是 v2，跑的是 V3） |
| 配置 | `/home/root/combined-v2-dryrun/user_data/config-dryrun-v2-server.json` |
| 交易数据库 | `/home/root/combined-v2-dryrun/user_data/tradesv3_dryrun_v2.sqlite` |
| 日志 | `/home/root/combined-v2-dryrun/user_data/logs/freqtrade.log` |
| API | `127.0.0.1:8081` |
| 策略 | 和本机 `user_data/strategies_v3/Combined_V3.py` 完全一致（sha256 以 `b45876…` 开头）；09-06 起没有改过 |

### 3.3 Telegram 监控（只读）

| 项 | 位置 |
|---|---|
| 脚本 | `/opt/nfi/scripts/tg_monitor.py`（仓库 `scripts/deploy/tg_monitor.py`） |
| Token 和 chat id | `/root/.tg_monitor.env`（权限 600，用户自己写的，**不要读取或外传**） |
| 定时器 | `tg-monitor-report.timer`：每天 01:00 UTC 检查，每 3 天发一次报告<br>`tg-monitor-alert.timer`：每 10 分钟检查一次，有问题才发 |
| 状态文件 | `/var/lib/tg_monitor/state.json` |
| 消息分类 | 🚨 告警 = 要看一下；ℹ️ 提示 = 按策略规则发生的（例如 doom 止损亏 8%），不用管 |
| 说明 | `reports/MONITORING_PLAN.md`；10-29 修过一次误报和漏报，见 `reports/TG_MONITOR_ISSUES_2026-10-29.md`（旧版备份 `/opt/nfi/scripts/tg_monitor.py.bak-20261029053614`） |
| 测试 | `python3 /opt/nfi/scripts/tg_monitor.py dry`：打印日报和告警模式会发的内容，不发送、不写状态 |

## 4. 代码仓库

| 项 | 值 |
|---|---|
| 本机路径 | `D:\NostalgiaForInfinity` |
| 远程仓库 | `https://github.com/orreland/nfi-x7safe.git`（公开仓库，只放脱敏后的内容） |
| 当前分支 | `exp/rebuy-ab-parity`，已同步到公开的 master |
| git 用户 | orreland |
| 未纳入 git | 上游策略原文件、`nfi_repo/`、行情数据、回测结果、`.venv`、`scratch/`、`reports/PRIVATE_NOTES.local.md` |

提交历史（从新到旧）：

```
5b03e24 Add dry-run parity, community comparison and mainstream-coin backtests
ac558db Fix Telegram monitor false alarms; record N25 verified on dry-run
879b2f9 Rebuy hard-stop grid, V3 round 2, follow-up plan
131f70c Evaluate upstream NFI X7 v17.5.185 under our safety layer
6d57ee3 Add read-only Telegram monitoring for the dry-run bots
9ec16a1 Add Combined_V3 exit/concurrency experiment and plain X7 summary
5b7bfa3 Rebuy experiments on the N25 + E10 base; runbook drill
7d5ae28 Record N25 + E10 going live on the dry-run server
76c2bae Deploy N25 to dry-run; add server deployment log
0a50bed Stop-variant experiments, MaxDrawdown equity mode, server sync, runbook
fbb8b01 Add rebuy A/B and backtest/dry-run parity check
bc1ccb9 Don't redistribute upstream base class; README already documents clone+cp
48f0319 Initial commit: X7Safe risk-fixed fork of NostalgiaForInfinityX7
```

## 5. 重要文件

### 5.1 策略代码

| 文件 | 内容 |
|---|---|
| `user_data/strategies/NostalgiaForInfinityX7Safe.py` | **服务器上正在跑的版本**：N25 + E10 + doom 止损 + 30 天时间止损 + 止损放行修复 + SAFE-TRIGGER 统计 |
| `user_data/strategies/NostalgiaForInfinityX7.py` | 上游原版 v17.4.543（不在 git 里，从 iterativv/NostalgiaForInfinity 获取） |
| `user_data/strategies/X7SafeStopVariants.py` | 所有回测实验用的变体（止损、rebuy、MaxDrawdown 等） |
| `user_data/strategies_up/` | 上游新版 v17.5.185 的评估副本（不在 git 里） |
| `user_data/strategies_v3/Combined_V3.py`、`Combined_V3_Variants.py` | V3 策略及其实验变体 |

### 5.2 配置

都在 `configs/` 下。

- **回测用的币种范围：**
  - `pairlist-survivorship-B-real-universe.json` + `blacklist-survivorship-test.json`：survB，80 个幸存币加 40 个已下架币；
  - `pairlist-backtest-static-binance-spot-usdt.json` + `blacklist-binance.json`：live，和服务器一致。
- **V3 回测：** `v3-backtest.json`、`v3-backtest-u20.json`。
- **服务器那边的覆盖配置：** `local-overrides-dryrun.json`。

### 5.3 脚本

| 文件 | 用途 |
|---|---|
| `scripts/run_stop_grid.sh` | 跑 X7 变体回测，用环境变量 `TIMERANGE`、`UNIVERSE`、`TAG` 控制 |
| `scripts/eval_grid.py`、`eval_stop_grid.py` | 评估回测：逐日盯市的回撤、收益/回撤比、Sharpe |
| `scripts/compare_parity.py` | 回测和模拟盘逐笔对账 |
| `scripts/rolling_window_returns.py` | 滚动窗口收益 |
| `scripts/fetch_delisted_data.py` | 下载已下架币的行情 |
| `pypatches/sitecustomize.py` | 省内存补丁（`FT_LOWMEM=1`），开不开结果逐笔一样 |
| `scripts/deploy/` | 部署说明 `DEPLOY.md`、**应急手册 `RUNBOOK_EMERGENCY.md`**（10-25 演练过）、`server_setup.sh`、服务模板、Telegram 脚本 |
| `tools/experiments/` | 各轮实验的队列和评估脚本（`scratch/tools/` 的存档） |

### 5.4 报告（建议按这个顺序读）

| 文件 | 内容 |
|---|---|
| `reports/X7_SUMMARY_PLAIN.md` | **先读这个**：X7 全过程的大白话总结 |
| `reports/FOLLOWUP_PLAN.md` | 后续计划和时间表 |
| `reports/DEPLOY_LOG.md` | 服务器上每一次改动；分析数据时按生效时间分段 |
| `reports/REBUY_AB_PARITY_2026-10-17.md` | 所有 X7 实验的完整记录（第 1~27 节） |
| `reports/REBUY_TESTS_DETAIL_2026-10-27.md` | rebuy 的 4 轮、14 种方案汇总 |
| `reports/UPSTREAM_EVAL_2026-10-26.md` | 上游新版评估：可以升级，但不急 |
| `reports/V3_EXIT_EXPERIMENT_2026-10-25.md`、`V3_ROUND2_2026-10-26.md` | V3 的两轮实验，结论是不改 |
| `reports/MONITORING_PLAN.md` | Telegram 监控方案 |
| `reports/TG_MONITOR_ISSUES_2026-10-29.md` | Telegram 消息里的误报 / 漏报排查与修复；N25 验证结果 |
| `reports/SAFE_ONLY.md`、`reports/archive/` | 早期的分析 |

### 5.5 本机的记录和数据

| 位置 | 内容 |
|---|---|
| `dryrun_backups/` | 从服务器拷下来的数据库快照：X7 截到 10-17 和 11-03，V3 截到 10-25 |
| `user_data/backtest_results/stopgrid-*`、`v3-*`、`up-*` | 约 250 个回测结果，1.3 GB |
| `user_data/data/binance/` | 5 分钟 K 线行情数据（feather 格式） |
| 根目录 `logs_*.log`、`scratch/tmp/log_*.log` | 各次回测的运行日志 |
| `.venv/` | Python 环境，freqtrade 2026.7 |

## 6. 备份

| 位置 | 内容 |
|---|---|
| 离线备份盘 `<离线备份盘>\NFI_backup_20261027\`（最新） | git bundle（全部历史，提交 `3634e6b`）、`files\`（代码和报告的明文副本）、`dryrun_backups\`、`scratch_tools\`、`README_恢复说明.txt` |
| 离线备份盘 `<离线备份盘>\NFI_backup_20261025\`、`<离线备份盘>\NFI_backup_20261026\` | 更早的两份 |
| 服务器 | 策略 `.bak-*` 文件；`DEPLOY_LOG.md` 副本 |
| GitHub | 公开仓库，脱敏后的完整历史；改写前的提交号对照见 `docs/HISTORY.md` |

恢复方法：`git clone <离线备份盘>\NFI_backup_20261027\NostalgiaForInfinity.bundle D:\NostalgiaForInfinity -b exp/rebuy-ab-parity`

## 7. 现在的策略状态

**X7Safe 当前规则（#4，2026-10-25 07:15:20 UTC 起生效）：**

- **N25：** 普通交易的硬止损是首仓价 −25%。
- **rebuy 交易：** 硬止损仍是首仓价 −15%，仓位是正常仓位的 0.25 倍。
- **E10：** MaxDrawdown 保护按账户权益计算，阈值 10%。
- **doom 止损**（亏 8% 离场）和 **30 天时间止损**。
- **止损交接：** 交易所止损单（`stoploss_on_exchange`）触发后，策略的 `confirm_trade_exit` 会放行。

**几个关键事实：**

- 回测和模拟盘对得上：X7 有 60/61 笔复现，V3 有 16/16 笔复现。回测略微偏乐观，大约每 7 周多 2%。
- 统计 N25 的效果时，**只算 10-25 07:15 UTC 之后开的交易**。
- **N25 已验证生效（10-29）：** 新规则下第一笔普通交易 GTC/USDT #74，交易所止损单直接挂在首仓价 ×0.750；rebuy 交易仍是 ×0.85。
  Telegram 日报每次都会把新规则下所有普通交易再查一遍。详见 `reports/TG_MONITOR_ISSUES_2026-10-29.md`。

**已经测过、决定不改的：**

- rebuy 的 14 种处理方式（rebuy 止损 −12% 最接近通过，等复验）；
- V3 的出场和并发方案（PC 方案等新数据复验）；
- 上游新版先不急着升级。

## 8. 时间表

| 时间 | 事项 |
|---|---|
| 11-09、11-23、12-07 | 两周一次的回测和模拟盘对账 |
| **11-22** | N25 中期检查 |
| **12-20** | N25 正式评估；复验 V3 PC 和 rebuy −12%；决定上游要不要升级、rebuy 要不要关 |
| **2027-01-05 前** | 决定服务器续费还是换机器 |

详见 `reports/FOLLOWUP_PLAN.md`。

## 9. 出事了怎么办

按 `scripts/deploy/RUNBOOK_EMERGENCY.md` 操作，分三级：

- **L1：** 停止开新仓（`stopentry`）；
- **L2：** 全部平仓（`forceexit all`）；
- **L3：** 停掉服务和容器。

**回滚 N25**（退回到只有 E10 的版本）：

```bash
install -o nfi -g nfi -m 644 /opt/nfi/user_data/strategies/NostalgiaForInfinityX7Safe.py.bak-20261018164737 /opt/nfi/user_data/strategies/NostalgiaForInfinityX7Safe.py
```

然后在**空仓时**执行 `python3 /opt/nfi/scripts/nfi_safe_restart.py`，并在 `DEPLOY_LOG.md` 里记一笔。

## 10. 踩过的坑

- **内存不够（OOM）：** 不要并行跑回测。用户开着 其他软件时，内存会更紧张。
- **不要编辑正在运行的 shell 脚本**，bash 是边读边执行的，改了会报错。
- **回测结果是 zip：** `eval_grid` 只认解压后的 json，先用 `scratch/tools/unzip_results.py` 解压。
- **自定义止损的写法：** `custom_stoploss` 只能在首仓成交的那次 after_fill 调用里动止损，否则会改到其他交易。
- **Windows 页面文件：** 挪到 D 盘没有生效，已改回自动管理。
- **路径：** 本机的 Git Bash 路径写 `/d/NostalgiaForInfinity`；配置文件里有中文注释，要设 `PYTHONUTF8=1`。
- **服务器日志每天 00:00 UTC 轮转：** `dryrun.log` 会被清空，前一天的内容在 `dryrun.log.1`，更早的是 `.gz`。
  查历史记录要用 `zgrep 关键字 /opt/nfi/user_data/logs/dryrun.log*`，只 grep 当前文件会漏。

---

以上为技术交接说明，不构成投资建议。
