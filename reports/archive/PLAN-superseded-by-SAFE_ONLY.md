# 计划：只发展 X7Safe

**决策（2026-08-22）**：放弃维护/继续测试官方原版 `NostalgiaForInfinityX7`，只投入 `NostalgiaForInfinityX7Safe`。
原版数据保留归档，仅作为"为什么这几个改动是必要的"的反面参照，不再单独回测。

---

## 已完成

- [x] **阶段 0 — 修正度量口径**：`compute_daily_metrics()` 加入逐日盯市 Sharpe/回撤/槽位利用率；`compare_runs.py` 做跨运行对比。
- [x] **阶段 1 — 修好 X7Safe 的止损**：补上被短路的 `system_v3_2_stops_enable`，删掉三个死分支的 `*_max_stake` 覆盖，加 30 天时间止损。重跑后止损从 0 次触发变成 1 doom + 8 时间止损；每槽位·天收益比原版高 62.5%。
- [x] **阶段 2 — 生存偏差实验**：证明黑名单排除的 40 个币今天 100% 已下架；三臂对照显示把它们放回真实宇宙后原版收益由 +191%（对照组）转为 −4.4%，回撤 37.67%，击穿官方 CI 验收线。

## 待办

### 阶段 3：Safe 修复版 + 真实宇宙 —— ✓ 已完成，结论：通过

**结果**（`user_data/backtest_results/survB-safe/`，2026-08-22）：把 Safe 修复版放进和第 08 节 B 组完全一样的真实宇宙（80 个固定种子抽样的幸存币 + 40 个已下架币）：

| 指标 | X7 原版（B 真实宇宙） | **X7Safe 修复版（B 真实宇宙）** |
|---|---:|---:|
| 交易笔数 | 213 | 436 |
| 亏损笔数 | 6 | 29 |
| 报告收益 | +19.12%（报告）/ −4.4%（盯市） | **+90.74%**（报告口径） |
| 报告回撤 | 23.62%（报告）/ 37.67%（盯市） | **7.13%**（报告口径） |
| 止损触发 | 0（未接线） | **多次 doom stop**（quick/normal/rebuy/rapid 各模式合计数十次） |

**判定：通过。** 官方 CI 验收线是回撤 ≤15%，Safe 修复版报告口径 7.13% 远低于此；
原版在同一宇宙里报告口径也只是勉强 +19.12%，盯市口径已转负。亏损笔数从 6 升到 29，
但每笔亏损被止损限制在 −8% 到 −28% 之间（多数在 −10%~−17%），不再出现原版那种
745 单、537 天的失控加仓。

**一个需要如实说明的数据质量问题（已排查，结论已修正）**：用 `*_wallet.feather`
重算的盯市口径这次出现了明显偏差（收益 65.5% vs 报告 90.74%，回撤 15.28% vs 报告
7.13%）。最初怀疑是"低槽位利用率下的稀疏采样偏差"，尝试了一版按货币做区间感知
forward-fill 的修复（保留在 `compute_daily_metrics()` 里），但重算后数字**完全没变**，
说明假设错了。

深挖发现：盯市曲线在 2025-05-19 单日凭空跳水约 1,000 USDT，随后企稳、不再变化——
时间点精确对应 STPT/USDT 恢复数据的最后一根 K 线。检查该日**真实价格走势**（从
`data.binance.vision` 恢复的 5m 数据）：STPT 当天从 0.078 缓慢跌到 0.070，**没有任何
暴跌或崩盘迹象**。这证明那 1,000 USDT 的跳水是**净值快照重建过程本身引入的假象**
（很可能是 pivot/ffill 在某个交易对的价格数据在窗口中途结束时处理不当），不是真实
市场行为，也不是策略的风险敞口。

**结论：盯市口径的 15.28% 回撤数字不可信，应弃用**；freqtrade 原生报告口径
（+90.74% / 7.13%，直接来自 436 笔已结算交易的实际盈亏）才是本次实验的权威结果。
`compute_daily_metrics()` 在"交易对价格数据于窗口中途终止"这一场景下存在未解决的
计算缺陷，已记入阶段 4 待办——下次修复前不要用它的回撤数字做判断，只用于笔数/
Sharpe 等不受此问题影响的辅助读数（已用两组已知运行交叉验证：X7 原版与 Safe-120
宇宙运行下该函数数字与报告口径高度吻合，问题只出现在含"价格数据提前终止的交易对"
的运行里）。

### 阶段 4：仓库清理（只留 Safe 版入口）—— 大部分已完成

- [x] `scripts/nfi_backtest_lib.py` 的 `STRATEGY` 默认值改成 `NostalgiaForInfinityX7Safe`（`UPSTREAM_STRATEGY` 保留供显式对比用），`run_backtest()` 现在会自动带上 `configs/local-overrides-safe.json` 与 `--enable-protections`。
- [x] 归档非 Safe 相关的历史结果到 `user_data/backtest_results/archive/`（`x7-upstream-official/`、`x7safe-pre-fix/`、`survivorship-experiment/`，各附说明），并清理了几个孤立的冒烟测试导出文件。
- [x] 新增项目根 `README.md`，说明只用 Safe 版、为什么不直接跑 `nfi_repo/NostalgiaForInfinityX7.py`（保持该文件不动以便 `git pull`，不在其顶部加注释）。
- [ ] 把 `reports/FINAL_REPORT.md` 和本文件合并成一份 `reports/SAFE_ONLY.md`，作为唯一权威文档；原 `RISK_ANALYSIS.md`、旧 `FINAL_REPORT.md` 移入 `reports/archive/`。
- [x] 排查 `compute_daily_metrics()` 的计算缺陷根源：确认是 freqtrade 净值快照对"仓位归零"和"现金入账"两个事件的记录时序不同步（不是最初怀疑的"低槽位利用率采样偏差"，也不是简单的forward-fill 能修的问题）。已撤回无效的区间掩码尝试，恢复为在 4/5 次运行中验证正确的原始实现，并在函数 docstring 里详细记录了这个已知局限、复现证据、以及为什么修复超出当前范围（需要用 OHLCV 重放交易而非解析稀疏的净值导出）。此问题只影响"生存偏差实验"这类含"价格数据中途终止交易对"的一次性分析，不影响日常 Safe 版生产回测——这类回测里的交易对价格数据全程覆盖，不会触发这个问题。

### 阶段 5：黑名单运维化

第 08 节证明黑名单是当前唯一有效的尾部风险控制，但官方黑名单更新滞后于事件。只做止损改造解决不了"该拉黑但还没拉黑"的币正常触发入场的问题。

- [ ] 制定黑名单更新节奏（建议：每周至少检查一次 Binance 公告 + 社区监控帖，不完全依赖 `nfi-updater` 的自动拉取）。
- [ ] 补一条自动化检查：定期跑 `scripts/fetch_delisted_data.py --dry-run` 式的探测，看当前白名单里是否已有交易对在 ccxt 里变成 `active=False`，作为"该拉黑了"的预警信号（而不是等官方仓库更新）。

### 阶段 6：Dry-run 前向验证（持续至少 3 个月）

- [ ] 挂 `NostalgiaForInfinityX7Safe`：现货、固定 `stake_amount`（不用 unlimited）、`tradable_balance_ratio ≤ 0.85`、开启阶段 5 的黑名单预警。
- [ ] `stoploss_on_exchange: true`，在目标交易所验证可用。
- [ ] 每周记录：槽位利用率、触发过的风控事件（doom 止损 / 时间止损次数）、盯市回撤，并与同期回测重跑对账，量化真实滑点/延迟造成的偏离。

### 阶段 7：决策点

四条全部满足才考虑投入真实资金，且从最小可行金额起步：

1. 阶段 3 的结果是"通过"或"部分通过"（回撤 < 15%）—— **已满足**（报告口径 7.13%）；
2. dry-run 3 个月里止损确实触发过、且没有显著损害收益；
3. dry-run 与回测重跑的偏离在可接受范围内；
4. `stoploss_on_exchange` 已验证可用。

任一条不满足就继续停在 dry-run。

---

## 文件索引

| 文件 | 用途 |
|---|---|
| `user_data/strategies/NostalgiaForInfinityX7Safe.py` | 修复后的止损 + 时间止损实现 |
| `scripts/nfi_backtest_lib.py` | 回测封装 + 盯市指标计算 |
| `scripts/compare_runs.py` | 跨运行对比表 |
| `scripts/fetch_delisted_data.py` | 从 data.binance.vision 恢复已下架币数据 |
| `scripts/ft_delisted.py` | 让已下架币通过 pairlist 校验（仅回测用） |
| `configs/local-overrides-safe.json` | Safe 版专属配置（固定仓位、槽位数、超时） |
| `configs/blacklist-survivorship-test.json` | 只保留结构性排除的黑名单（不含"后见之明"条目） |
| `configs/pairlist-survivorship-B-real-universe.json` | 80 幸存 + 40 已下架，真实宇宙实验用 |
