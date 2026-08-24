#!/usr/bin/env python
"""eval_grid.py - score the pre-registered drawdown-reduction grid.

Applies the pass criteria fixed in reports/SAFE_ONLY.md 待办1d BEFORE any
result was seen, so a variant cannot be talked into looking good after the
fact:

  1. return/drawdown ratio must beat the baseline's 18.2
     (drawdown alone is not enough - de-leveraging always lowers drawdown,
     round 1's LowerStake proved that and was still a worse trade)
  2. neither half-period may get worse
     (the sample has exactly ONE dominant drawdown event, in H1. A variant
     that only helps H1 while H2 degrades is fitting that single event)
  3. Sharpe >= baseline - 0.1

Splits at 2025-11-16, the midpoint of the 18-month window.

USAGE
  .venv\\Scripts\\python.exe scripts\\eval_grid.py
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nfi_backtest_lib import USER_DATA, _rebuild_equity_curve  # noqa: E402

SPLIT = pd.Timestamp("2025-11-16", tz="UTC")

# Fixed in 待办1d before the grid was run.
BASELINE_RATIO = 18.2
BASELINE_SHARPE = 3.29
SHARPE_FLOOR = BASELINE_SHARPE - 0.1

RUNS = [
  ("基线 (doom .08)", "survB-safe-percent"),
  ("D1 doom .05", "grid-X7SafeDoom05"),
  ("D1 doom .12 +dr4", "grid-X7SafeDoom12"),
  ("D1 doom .20 +dr4", "grid-X7SafeDoom20"),
  ("D2 预知 7 天", "grid-X7SafeForeknow7"),
  ("D2 预知 30 天", "grid-X7SafeForeknow30"),
  ("D3 熔断 24h/5%", "grid-X7SafeBreakerTight"),
  ("D3 熔断 7d/12%", "grid-X7SafeBreakerLong"),
]


def _result_json(run_dir: str):
  hits = [
    f
    for f in glob.glob(f"user_data/backtest_results/{run_dir}/backtest-result-*.json")
    if "_config" not in f and "meta" not in f
  ]
  return hits[0] if hits else None


def _dd(curve: pd.Series) -> float:
  return float(-(curve / curve.cummax() - 1).min() * 100)


def analyse(run_dir: str) -> dict | None:
  path = _result_json(run_dir)
  if path is None:
    return None
  stats = next(iter(json.loads(Path(path).read_text(encoding="utf-8"))["strategy"].values()))
  eq = _rebuild_equity_curve(stats, USER_DATA / "data" / "binance")
  if eq is None or len(eq) < 3:
    return None

  r = eq.pct_change().dropna()
  ret = float((eq.iloc[-1] / eq.iloc[0] - 1) * 100)
  dd = _dd(eq)
  return {
    "ret": ret,
    "dd": dd,
    "ratio": ret / dd if dd else float("nan"),
    "sharpe": float(r.mean() / r.std() * np.sqrt(365)) if r.std() else float("nan"),
    "dd_h1": _dd(eq.loc[:SPLIT]),
    "dd_h2": _dd(eq.loc[SPLIT:]),
    "trades": len(stats.get("trades") or []),
    "losses": stats.get("losses", 0),
    # Sanity: reconstruction must agree with freqtrade's own final balance.
    "recon_err": abs(eq.iloc[-1] - stats["final_balance"]) / stats["final_balance"] * 100,
  }


def main() -> int:
  rows = []
  for label, run_dir in RUNS:
    res = analyse(run_dir)
    if res is None:
      print(f"[skip] {label} - no result yet ({run_dir})")
      continue
    rows.append((label, res))

  if not rows:
    print("没有可评估的结果。")
    return 1

  base = rows[0][1]
  print(
    f"{'变体':22s}{'收益':>9s}{'回撤':>8s}{'收/撤':>8s}{'Sharpe':>8s}"
    f"{'H1回撤':>8s}{'H2回撤':>8s}{'笔数':>6s}{'校验':>7s}  判定"
  )
  print("-" * 104)
  for label, m in rows:
    if label.startswith("基线"):
      verdict = "(baseline)"
    else:
      fails = []
      if m["ratio"] <= BASELINE_RATIO:
        fails.append("收/撤未超基线")
      if m["dd_h1"] > base["dd_h1"] + 1e-9 or m["dd_h2"] > base["dd_h2"] + 1e-9:
        fails.append("半期变差")
      if m["sharpe"] < SHARPE_FLOOR:
        fails.append("Sharpe不足")
      verdict = "[PASS] 通过三条标准" if not fails else "[FAIL] " + " / ".join(fails)
    print(
      f"{label:22s}{m['ret']:8.2f}%{m['dd']:7.2f}%{m['ratio']:8.1f}{m['sharpe']:8.2f}"
      f"{m['dd_h1']:7.2f}%{m['dd_h2']:7.2f}%{m['trades']:6d}{m['recon_err']:6.2f}%  {verdict}"
    )

  print(
    f"\n判定门槛（预注册）：收益/回撤 > {BASELINE_RATIO} 且 两个半期回撤都不劣于基线"
    f"（H1 {base['dd_h1']:.2f}% / H2 {base['dd_h2']:.2f}%）且 Sharpe >= {SHARPE_FLOOR:.2f}"
  )
  print(
    "提醒：样本内只有一个主导回撤事件（2025-04-08，位于 H1）。"
    "'H2 不变差' 只能证伪明显的过拟合，不能正面证明变体在下次危机有效。"
  )
  return 0


if __name__ == "__main__":
  sys.exit(main())
