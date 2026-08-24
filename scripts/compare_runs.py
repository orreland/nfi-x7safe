#!/usr/bin/env python
"""compare_runs.py - build one comparison table across every backtest run in
user_data/backtest_results/, using BOTH metric conventions side by side.

Why both: freqtrade's headline Sharpe / max-drawdown are computed over the
per-trade profit_ratio series. For a strategy that grinds (hundreds of orders
inside one trade) those numbers are systematically distorted -- the ratio's
denominator inflates with every order, and unrealized losses on open positions
never touch the curve at all. The mark-to-market columns recompute the same
quantities from a daily equity curve rebuilt from order flow (the
*_wallet.feather export is unreliable - see nfi_backtest_lib._rebuild_equity_curve).

Also reports slot occupancy, which is the failure mode this strategy actually
exhibited (3 trades held 89% of all slot-days across 18 months) and which no
standard metric surfaces.

USAGE
  .venv\\Scripts\\python.exe scripts\\compare_runs.py
  .venv\\Scripts\\python.exe scripts\\compare_runs.py --filter single --md reports/comparison.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nfi_backtest_lib import USER_DATA, compute_daily_metrics  # noqa: E402


def load_runs(results_dir: Path, name_filter: str | None) -> list[dict]:
  runs = []
  for run_dir in sorted(results_dir.iterdir()):
    if not run_dir.is_dir():
      continue
    if name_filter and name_filter not in run_dir.name:
      continue
    candidates = [
      p for p in run_dir.glob("backtest-result-*.json")
      if "_config" not in p.name and "meta" not in p.name
    ]
    if not candidates:
      continue
    path = max(candidates, key=lambda p: p.stat().st_mtime)
    try:
      data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
      continue
    block = data.get("strategy", {})
    if not block:
      continue
    strategy_name, stats = next(iter(block.items()))

    trades = stats.get("trades") or []
    exit_reasons: dict[str, int] = {}
    for t in trades:
      reason = str(t.get("exit_reason", "")).split(" (")[0]
      exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

    runs.append(
      {
        "run": run_dir.name,
        "strategy": strategy_name,
        "trades": stats.get("total_trades") or len(trades),
        "wins": stats.get("wins", 0),
        "losses": stats.get("losses", 0),
        "profit_pct": (stats.get("profit_total") or 0.0) * 100,
        "max_open": stats.get("max_open_trades"),
        "reported_sharpe": stats.get("sharpe"),
        "reported_dd_pct": (stats.get("max_drawdown_account") or 0.0) * 100,
        "daily": compute_daily_metrics(str(path), stats),
        "exit_reasons": exit_reasons,
        "path": str(path),
      }
    )
  return runs


def fmt(v, spec="7.2f", dash="—"):
  return dash if v is None else format(v, spec)


def render(runs: list[dict]) -> str:
  lines: list[str] = []
  lines.append("# 回测运行对比\n")
  lines.append(
    "两套口径并列。**报告口径**是 freqtrade 基于每笔交易 profit_ratio 算的"
    "（忽略未平仓浮亏，系统性低估风险）；**盯市口径**是从订单流重建的逐日净值算的"
    "（回放每笔成交得到持仓，用各交易对日收盘价标记市值），含未平仓浮亏。\n\n"
    "> 注：盯市回撤与 NFI 官方 CI 的 ≤15% 验收线**不是同一口径**，不能直接比较——"
    "官方那条线定义在 freqtrade 的已实现口径上。\n"
  )
  lines.append("| 运行 | 策略 | 笔数 | 胜/负 | 总收益 | Sharpe(报告) | **Sharpe(盯市)** | 回撤(报告) | **回撤(盯市)** | 年化波动 | 槽位利用率 | 最长持仓 |")
  lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
  for r in runs:
    d = r["daily"]
    lines.append(
      f"| `{r['run']}` | {r['strategy'].replace('NostalgiaForInfinity','NFI')} "
      f"| {r['trades']} | {r['wins']}/{r['losses']} "
      f"| {fmt(r['profit_pct'], '+.2f')}% "
      f"| {fmt(r['reported_sharpe'], '.2f')} "
      f"| **{fmt(d.get('daily_sharpe'), '.2f')}** "
      f"| {fmt(r['reported_dd_pct'], '.2f')}% "
      f"| **{fmt(d.get('daily_max_drawdown_pct'), '.2f')}%** "
      f"| {fmt(d.get('daily_ann_volatility_pct'), '.2f')}% "
      f"| {fmt(d.get('slot_utilization_pct'), '.1f')}% "
      f"| {fmt(d.get('longest_trade_days'), '.0f')}d |"
    )

  lines.append("\n## 槽位占用明细\n")
  lines.append("| 运行 | 槽位·天(已用/容量) | 前 3 笔占比 | >1% 回撤天数 |")
  lines.append("|---|---:|---:|---:|")
  for r in runs:
    d = r["daily"]
    used, cap = d.get("slot_days_used"), d.get("slot_days_capacity")
    lines.append(
      f"| `{r['run']}` | {fmt(used, '.0f')} / {fmt(cap, '.0f')} "
      f"| {fmt(d.get('slot_days_top3_share_pct'), '.1f')}% "
      f"| {d.get('days_in_drawdown_gt_1pct', '—')} |"
    )

  lines.append("\n## 风控触发情况\n")
  lines.append(
    "只有**触发过**的风控才算被验证。下面统计每次运行里可归因于止损类退出的笔数。\n"
  )
  lines.append("| 运行 | force_exit | 含 stoploss 的退出 | 时间止损 | 其他退出种类数 |")
  lines.append("|---|---:|---:|---:|---:|")
  for r in runs:
    er = r["exit_reasons"]
    force = sum(v for k, v in er.items() if k == "force_exit")
    stops = sum(v for k, v in er.items() if "stoploss" in k)
    tstop = sum(v for k, v in er.items() if "time_stop" in k)
    lines.append(f"| `{r['run']}` | {force} | {stops} | {tstop} | {len(er)} |")

  return "\n".join(lines) + "\n"


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--filter", help="only runs whose directory name contains this")
  ap.add_argument("--md", help="also write the table to this markdown file")
  args = ap.parse_args()

  runs = load_runs(USER_DATA / "backtest_results", args.filter)
  if not runs:
    print("No backtest results found.")
    return 1
  out = render(runs)
  print(out)
  if args.md:
    Path(args.md).write_text(out, encoding="utf-8")
    print(f"written: {args.md}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
