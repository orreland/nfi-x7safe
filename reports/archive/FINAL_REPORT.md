# NostalgiaForInfinity X7 回测研究报告

策略: NostalgiaForInfinityX7 | 市场: Binance 现货 USDT | 区间: 2025-02-16 ~ 2026-08-16 | 模式: dry-run

## 执行摘要

- 18个月连续回测: +142.31% 收益, 胜率 99.07% (320胜/3负), 最大回撤 2.63%, Sharpe 9.13, 同期基准 -72.93%
- Walk-forward 10窗口 (60-60-45设计): 9/10 通过全部四条标准, 判定 ROBUST
- 蒙特卡洛 5000次模拟: 收益中位数 142.2%, 5%-95%分位 [126.4%, 158.7%], 无一次亏损
- 手续费压力测试 (3个月子样本): 0.1%->0.2%手续费, 收益从9.23%降到6.73%, 仍保持正收益/正Sharpe
- 持仓集中度: 82个实际交易对里, Top10贡献49.1%利润, DASH/USDT一家占14.4%

**关键风险发现**: 全部323笔交易里唯一的3笔"亏损", 全部来自回测结束瞬间的强制平仓(force_exit)。
策略从未主动止损, 靠网格加仓摊薄成本"扛单"直到解套。2.63%的最大回撤和99%的胜率很可能系统性
低估了实盘中的资金占用风险和尾部风险。详见完整报告。

完整报告(含方法论、问题排查细节、全部图表): 见本次对话中发布的 Artifact 页面。

## 文件清单

- `scripts/nfi_backtest_lib.py` - 共用库
- `scripts/run_backtest.py` - 18个月单次回测
- `scripts/run_walk_forward.py` - 10窗口walk-forward验证
- `scripts/run_monte_carlo.py` - 蒙特卡洛稳健性模拟
- `scripts/run_stress_test.py` - 手续费敏感性 + 持仓集中度分析
- `pypatches/sitecustomize.py` - 本地ccxt兼容补丁 (通过PYTHONPATH注入,不修改已安装依赖)
- `reports/backtest_summary_20250216-20260816.json` - 18个月回测摘要
- `reports/walk_forward_report_20260816.json` - walk-forward完整结果
- `reports/monte_carlo_backtest_summary_20250216-20260816.json` - 蒙特卡洛结果
- `reports/stress_test_20260516-20260816.json` - 压力测试结果

## 复现方式

```
.venv\Scripts\python.exe scripts\run_backtest.py --start 20250216 --end 20260816
.venv\Scripts\python.exe scripts\run_walk_forward.py --end 20260816
.venv\Scripts\python.exe scripts\run_monte_carlo.py --result reports\backtest_summary_20250216-20260816.json --sims 5000
.venv\Scripts\python.exe scripts\run_stress_test.py --start 20260516 --end 20260816
```

以上内容为策略回测与技术风险分析, 不构成投资建议。

## 附录: 安全版对比验证 (2026-08-19)

对官方原版与风控收紧版(NostalgiaForInfinityX7Safe)做了完全对照的18个月回测 + 10窗口walk-forward重跑。

**核心数字对比:**

| 指标 | 原版 | 安全版 | 备注 |
|------|------|--------|------|
| 总收益 | +142.31% | +64.19% | 差异来自仓位收缩,非风控生效 |
| 交易笔数 | 323 | 274 | — |
| 胜率 | 99.07% | 98.91% | 两版亏损的是**同样 3 笔** |
| 最大回撤(报告口径) | 2.63% | 3.84% | 按笔计算,低估 |
| **最大回撤(逐日盯市)** | **4.65%** | **3.13%** | 含未平仓浮亏,真实口径 |
| 最大回撤(绝对USDT) | 653.84 → 盯市 769.6 | 656.08 → 盯市 509.8 | — |
| Sharpe(报告口径) | 9.13 | 5.06 | 按笔计算,虚高 |
| **Sharpe(逐日盯市)** | **3.23** | **2.73** | 真实口径 |
| 年化波动率(盯市) | 18.84% | 12.45% | — |
| 槽位利用率 | 35.1% (6槽) | 52.3% (4槽) | 两版都被同 3 笔僵尸吃掉 1,029.5 槽位·天 |
| Walk-forward通过率 | 9/10 | 9/10 | 失败的是同一个窗口 #7 |
| WF 平均 OOS 收益 | 10.81% | 7.23% | — |

**关键发现**: 逐一检查11份完整运行日志后确认, 安全版新增的硬止损(-15%)、
收紧后的末日止损、以及三项账户级熔断保护, 在这次18个月历史中**全部0次触发**。
收益下降完全来自"仓位从unlimited改成固定金额"的资金收缩效应, 而非风控机制
真正规避了某次亏损。回撤百分比升高(2.63%→3.84%)也只是同一场约654 USDT的
force_exit回撤, 除以更小的账户峰值(24885→17075)所致, 不是新增了风险。

**结论**: 这次对比验证了配置改动本身没有引入bug、机制能正常运行, 但**没有
验证**这些风控在真正极端行情下是否有效 —— 因为这段历史里从未出现过需要
它们出手的场景。

完整对比报告: 见本次对话中发布的第二份 Artifact 页面。
数据来源:
- reports/backtest_summary-NostalgiaForInfinityX7Safe_20250216-20260816.json
- reports/walk_forward_report-NostalgiaForInfinityX7Safe_20260816.json
- user_data/strategies/NostalgiaForInfinityX7Safe.py
- configs/local-overrides-safe.json

## 附录 2: 代码核实发现的两处问题 (2026-08-22)

逐行读完 `NostalgiaForInfinityX7.py` (77,198 行) 后确认了两件之前报告没说对的事。

### 问题 1: X7Safe 的止损从未接上电 (已修复,见下)

X7Safe 把 `system_v3_2_stop_threshold_doom_spot` 从 0.12 收紧到 0.08,
但**没有同时设 `system_v3_2_stops_enable = True`**。而当前生效的系统版本正是 v3_2:

```python
# NostalgiaForInfinityX7.py:44105 (long_exit_stoploss)
if is_system_v3_2:
    if self.system_v3_2_stops_enable and (profit_stake < -(entry_cost * 0.08)):
        return True, stoploss_doom
# 但 X7.py:583 → system_v3_2_stops_enable = False  ← 整个条件被 and False 短路
```

所以那个收紧后的阈值**从未参与过任何判断**。FINAL_REPORT 原文说"新增风控 0 次触发,
因为这段历史没出现需要它出手的场景"—— 真实原因有一半是**它压根没接上电**。

同理,`grinding_v1_max_stake` / `grinding_v2_max_stake` / `system_v3_1_max_stake`
三个覆盖也都落在死分支上(当前只有 `system_v3_max_stake` 生效)。
X7Safe 里真正起作用的改动只有 `stoploss = -0.15`(freqtrade 层)和配置里的仓位收缩。

**旁证**:X7Safe 的逐笔明细里,亏损的还是 COTI / CRV / RAD 这**同样 3 笔**,
持仓天数完全一致(537.1 / 382.4 / 3.7 天),订单数只因固定仓位小幅减少(745→652, 169→165)。
持仓行为和原版几乎一模一样,正是因为风控没生效。

### 问题 2: grinding 不是马丁格尔 (RISK_ANALYSIS.md 的核心假设有误)

`X7.py:47269` 的 `system_v3_max_stake = 1.0` 把单笔持仓市值封顶在首笔入场成本。
`reports/RISK_ANALYSIS.md` 里"加仓无限制吞噬账户"的推演在当前代码下不成立,
该文档已加事实修正标注。真实风险是**槽位僵尸化**(已在两版回测中各自实测)。
