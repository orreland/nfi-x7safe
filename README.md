# NostalgiaForInfinity 回测与风险分析项目

基于 [iterativv/NostalgiaForInfinity](https://github.com/iterativv/NostalgiaForInfinity)
（fork 自 commit `296b962`，2026-08-15）的独立风险审计、bug 修复与回测方法论修正。
License: GPLv3（见 [LICENSE](LICENSE)），继承自上游同一协议。

**当前唯一建议使用的策略是 `NostalgiaForInfinityX7Safe`**（`user_data/strategies/NostalgiaForInfinityX7Safe.py`）。
详见 `reports/SAFE_ONLY.md`——里面完整记录了包括我自己犯过的两轮回测度量计算
bug 在内的所有过程，不只是最终结论。

## 这个仓库不包含什么，为什么

- **upstream 策略代码本身**（`NostalgiaForInfinityX7.py` 等）不在这里，请自行克隆：
  ```bash
  git clone https://github.com/iterativv/NostalgiaForInfinity.git nfi_repo
  cp nfi_repo/NostalgiaForInfinityX7.py user_data/strategies/
  ```
  `user_data/strategies/NostalgiaForInfinityX7Safe.py` 通过继承这个基类工作。
- **历史行情数据 / 回测结果原始 JSON** 不在这里（体积大且可复现）。用
  `scripts/fetch_delisted_data.py`（含 40 个已下架币的数据恢复）和
  `scripts/run_backtest.py` 自行生成；`reports/` 里保留了已跑出的汇总数字。

## 为什么不直接用官方原版

`nfi_repo/NostalgiaForInfinityX7.py` 是上游仓库的原样克隆，**故意保持不动**以便
`git pull` 持续可用——不要直接编辑这个文件。它只作为 `NostalgiaForInfinityX7Safe`
的基类被继承，不建议单独运行/回测。

原因（详见 `reports/comparison-all-runs.md` 与已发布的 Artifact 拆解报告）：

1. **默认无止损。** `stoploss=-0.99`、`system_v3_2_stops_enable=False`、
   `u_e_stops_enable=False`——官方默认配置下没有任何会主动止损离场的路径。
2. **收益依赖生存偏差。** 官方黑名单排除的 40 个交易对，今天 100% 已从币安
   现货下架。三臂对照实验显示：把这些币放回同规模的"真实宇宙"后，原版收益
   从 +191%（对照组）变成 −4.4%，最大回撤 3.70% → 37.67%，击穿官方 CI 自己
   ≤15% 的验收线。

`NostalgiaForInfinityX7Safe` 修复了止损开关未接线的 bug，加了 30 天时间止损，
仓位改为按账户权益百分比动态计算（默认 15%/笔，上限 $4500），而不是固定金额。

## 目录速览

- `user_data/strategies/NostalgiaForInfinityX7Safe.py` — 当前策略
- `user_data/strategies/X7SafeVariants.py` — 预注册的降回撤对照实验变体（含明确标注
  "NOT DEPLOYABLE" 的对照组，用于验证方法而非直接部署）
- `scripts/` — 回测/验证工具链，含 `preflight.py`（dry-run 启动前检查）（详见各脚本文件头注释）
- `scripts/deploy/` — 云服务器部署脚本与步骤说明
- `configs/local-overrides-safe.json` — Safe 版专属配置（百分比仓位、槽位数）
- `configs/blacklist-survivorship-test.json` — **仅用于回测实验**、故意放行已下架币的黑名单，
  绝不能用于 dry-run/实盘启动命令
- `reports/SAFE_ONLY.md` — 完整决策记录，含三轮回测度量 bug 的发现与修正过程
- `reports/comparison-all-runs.md` — 跨运行指标对比（含生存偏差实验结果）

## ⚠️ 免责声明

这是个人回测与代码审计记录，不是投资建议，也不保证在实盘/dry-run 中复现回测数字——
`reports/SAFE_ONLY.md` 里专门记录了几个已知的回测与实盘会不一致的地方（比如
`OBV_change_pct` 指标对数据窗口起点的依赖）。加密货币交易有本金损失风险，任何配置
改动前建议先完整读一遍 `reports/SAFE_ONLY.md`。

## 快速开始

```bash
.venv\Scripts\python.exe scripts\run_backtest.py --start 20250216 --end 20260816
```

不传 `--strategy` 时默认跑 `NostalgiaForInfinityX7Safe`，并自动带上
`configs/local-overrides-safe.json` 和 `--enable-protections`。
如需跑官方原版做对比，显式传 `--strategy NostalgiaForInfinityX7`。
