# NFI X7Safe：策略、回测方法和完整研究记录

基于 [iterativv/NostalgiaForInfinity](https://github.com/iterativv/NostalgiaForInfinity) X7 的币安现货策略研究。
这里公开策略代码、回测方法、全部实验记录和模拟盘交易快照，目的是让别的团队或 AI 能复现、核对并继续改进。

*In English: a risk-audited fork of the NFI X7 freqtrade strategy, with every experiment, pre-registration and
dry-run snapshot published. Start at [docs/REPRODUCE.md](docs/REPRODUCE.md) to reproduce the baselines trade by trade,
and [docs/TEAM_HANDOFF.md](docs/TEAM_HANDOFF.md) to continue the work. Documents are mostly in Chinese.*

> **这不是投资建议，也不是能直接赚钱的机器人。** 目前只跑模拟盘（不动真钱），模拟盘至今是亏损的。
> 回测不含滑点，结果偏乐观。加密货币交易可能损失本金。

## 从哪里开始

| 你想做什么 | 看这里 |
|---|---|
| 了解全过程（大白话） | [reports/X7_SUMMARY_PLAIN.md](reports/X7_SUMMARY_PLAIN.md) |
| 复现回测，逐笔核对 | [docs/REPRODUCE.md](docs/REPRODUCE.md) |
| 接手改进任务（流程、任务、已放弃的方案） | [docs/TEAM_HANDOFF.md](docs/TEAM_HANDOFF.md) |
| 看发展历史 | [docs/HISTORY.md](docs/HISTORY.md) |
| 运维细节 | [reports/HANDOVER.md](reports/HANDOVER.md)、[reports/DEPLOY_LOG.md](reports/DEPLOY_LOG.md)、[scripts/deploy/](scripts/deploy/) |

## 现在的状态（2026-11-03）

- **策略：** [`NostalgiaForInfinityX7Safe`](user_data/strategies/NostalgiaForInfinityX7Safe.py)，继承上游 X7 v17.4.543（提交 `296b962`），再加安全层：
  - 普通交易硬止损：首仓价 −25%（N25）；rebuy 交易：−15%，仓位是正常的 0.25 倍；
  - doom 止损：亏损超过首仓成本的 8% 离场；
  - 30 天时间止损；
  - MaxDrawdown 保护按账户权益计算，阈值 10%（E10）；
  - 仓位是账户权益的 15%，最多 4 个仓位。
- **另一个策略：** [`Combined_V3`](user_data/strategies_v3/Combined_V3.py)，独立的 5 分钟抄底策略，同样只跑模拟盘。
- **模拟盘（X7Safe，1 万 USDT）：** 累计 78 笔、−1047 USDT。其中当前规则下 6 笔、−291 USDT，样本太小，不能下结论。
- **规则冻结：** 约 2026-12-20 正式评估之前不改规则。

## 主要结果

回测：逐日盯市，1 万 USDT、最多 4 个仓位，社区版不加安全层。数据和判定见 [对比报告](reports/PARITY_COMMUNITY_2026-11-03.md)、[主流币报告](reports/MAINSTREAM_TEST_2026-11-03.md)。

| 约 20 个月（2025-02-16 至 2026-11-03） | 收益 | 最大回撤 | 笔数 |
|---|---|---|---|
| **X7Safe，全币种（含 40 个已下架币）** | **+129%** | **10.3%** | 525 |
| 社区 X7 v17.5.206，全币种 | +3% | 19.7% | 142 |
| 社区 X8 v18.0.195，全币种 | +42% | 19.8% | 237 |
| X7Safe，14 个主流币 | +15% | 1.4% | 56 |
| 社区 X8，14 个主流币 | +29% | 0.8% | 48 |

**最近约 9 周，X7Safe 全币种 −5.5%，社区 X8 全币种 +8.7%。** 长期好不代表最近好，这个差异是下一步的研究方向。

**回测和模拟盘对账：** 当前规则下 6/6 笔都复现，但模拟盘亏 291 USDT、回测只亏 142 USDT。差额几乎都来自一笔开仓价差，详见报告。

**要打折看 +129%：** 模拟盘开仓平均比回测贵 0.51%。只把这个价差放进回测，X7Safe 就降到 **+85%、回撤 12.9%**；其中 2025 Q4 一个季度就涨了 65%。X8 + 安全层和长线趋势都没通过预注册标准，见 [实验报告](reports/EXPERIMENTS_2026-11-03.md)。

## 目录

| 位置 | 内容 |
|---|---|
| `user_data/strategies/` | X7Safe 和回测实验用的变体 |
| `user_data/strategies_v3/` | Combined_V3 和变体 |
| `user_data/strategies_up/` | 评估上游 v17.5.185 用的安全层副本 |
| `configs/` | 资金规则、币种名单、黑名单 |
| `scripts/` | 回测、评估、对账、取数据的工具 |
| `scripts/deploy/` | 部署说明、应急手册、监控脚本、定时器配置 |
| `tools/experiments/` | 各轮实验的队列和评估脚本（原样存档，路径写死为 `D:\NostalgiaForInfinity`） |
| `reports/` | 全部实验记录；`reports/baselines/` 是可核对的逐笔基准 |
| `dryrun_backups/` | 模拟盘数据库快照（只有模拟交易，没有账户信息） |

## 这个仓库不包含什么

- **上游策略文件：** 用 [`scripts/fetch_upstream.sh`](scripts/fetch_upstream.sh) 按固定提交取回，并校验 hash。
- **行情数据（约 700 MB）和回测原始结果（约 1.4 GB）：** 取数方法见 [docs/REPRODUCE.md](docs/REPRODUCE.md)。
- **服务器地址、密钥、账户信息：** 文档里用 `<服务器IP>` 这类占位符代替。

## 协议

GPLv3（见 [LICENSE](LICENSE)），继承自上游。
