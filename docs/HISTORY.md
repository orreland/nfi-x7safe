# 发展历史

时间都是 UTC。详细过程见 [reports/X7_SUMMARY_PLAIN.md](../reports/X7_SUMMARY_PLAIN.md)，服务器改动见 [reports/DEPLOY_LOG.md](../reports/DEPLOY_LOG.md)。

| 时间 | 事情 | 记录 |
|---|---|---|
| 2026-08-15 | 从上游 X7 v17.4.543（`296b962`）开始做风险审计 | `reports/archive/` |
| 2026-08-16~22 | 18 个月回测。发现官方黑名单排除的 40 个币后来全部下架（生存偏差）；发现 doom 止损没有接线（总开关关着）并修复；发现自己的回测度量 bug 并修正 | `reports/SAFE_ONLY.md` |
| 2026-08-24 | 服务器部署，X7Safe 开始模拟盘（首笔 08-30）。Combined_V3 随后在 09-06 启动 | `reports/DEPLOY_LOG.md` |
| 2026-09-30 | 发现交易所止损被策略拒绝，导致紧急市价离场（#1）；修复，并加每周受控重启 | `reports/DEPLOY_LOG.md` |
| 2026-10-13~18 | 对账：回测和模拟盘逐笔比较，60/61 笔复现。实验 rebuy 和止损方案 | `reports/REBUY_AB_PARITY_2026-10-17.md` |
| 2026-10-18~25 | MaxDrawdown 改按账户权益计算（E10，#3）；普通交易硬止损放宽到 −25%（N25，#4）。**10-25 07:15:20 同时生效，模拟盘新样本从这里开始** | 同上，第 14~21 节 |
| 2026-10-25 | 应急手册演练；上线 Telegram 监控 | `scripts/deploy/RUNBOOK_EMERGENCY.md` |
| 2026-10-25~27 | V3 出场和并发实验（不改）；上游 v17.5.185 评估（可以升级，但不急）；rebuy 14 种方案（不改） | `reports/V3_*`、`reports/UPSTREAM_EVAL_2026-10-26.md`、`reports/REBUY_TESTS_DETAIL_2026-10-27.md` |
| 2026-10-29 | 修 Telegram 监控的误报和漏报；**N25 验证生效**（交易所止损直接挂在首仓价 ×0.75） | `reports/TG_MONITOR_ISSUES_2026-10-29.md` |
| 2026-11-03 | 对账 6/6 复现，发现开仓价差问题；对比社区 X7 v17.5.206、X8 v18.0.195；主流币测试；仓库脱敏公开 | `reports/PARITY_COMMUNITY_2026-11-03.md`、`reports/MAINSTREAM_TEST_2026-11-03.md` |

## 提交号对照

2026-11-03 公开前，为了去掉私人信息（服务器地址、账户信息等），改写了当时还没公开的 11 个提交。
改写只替换了这些信息，策略代码没有变，提交的时间和作者也不变。**旧报告里如果出现左列的提交号，对应的是右列。**

| 改写前 | 改写后 | 内容 |
|---|---|---|
| `706e38e` | `fbb8b01` | Add rebuy A/B and backtest/dry-run parity check |
| `41d4c07` | `0a50bed` | Stop-variant experiments, MaxDrawdown equity mode, server sync, runbook |
| `48cd3a6` | `76c2bae` | Deploy N25 to dry-run; add server deployment log |
| `e8c938e` | `7d5ae28` | Record N25 + E10 going live on the dry-run server |
| `05c52e3` | `5b7bfa3` | Rebuy experiments on the N25 + E10 base; runbook drill |
| `b61b6c6` | `9ec16a1` | Add Combined_V3 exit/concurrency experiment and plain X7 summary |
| `bcdbb39` | `6d57ee3` | Add read-only Telegram monitoring for the dry-run bots |
| `70bcbab` | `131f70c` | Evaluate upstream NFI X7 v17.5.185 under our safety layer |
| `3634e6b` | `879b2f9` | Rebuy hard-stop grid, V3 round 2, follow-up plan |
| `b7bc914` | `ac558db` | Fix Telegram monitor false alarms; record N25 verified on dry-run |
| `e5f6d25` | `5b03e24` | Add dry-run parity, community comparison and mainstream-coin backtests |
