#!/usr/bin/env python
"""eval_stop_grid.py - compare the X7SafeStopVariants runs against the
"stop denied" reference (survB-safe-percent).

Reuses eval_grid.analyse() for the mark-to-market equity metrics and adds the
two things this grid is about: how often the hard stop fired, and what
rebuy-mode trades contributed.

USAGE
  .venv\\Scripts\\python.exe scripts\\eval_stop_grid.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_grid import _result_json, analyse  # noqa: E402

REBUY_TAGS = {"61", "62", "63", "64", "65", "68"}

RUNS = [
  ("回测旧基线(止损被拒)", "survB-safe-percent"),
  ("现状(15%止损生效)", "stopgrid-X7SafeStopHonored"),
  ("方案2 关rebuy+15%", "stopgrid-X7SafeStopHonoredNoRebuy"),
  ("方案3 止损12%", "stopgrid-X7SafeStop12"),
  ("对照 止损25%", "stopgrid-X7SafeStop25"),
  ("旧基线去掉rebuy", "stopgrid-X7SafeNoRebuy"),
  ("方案2b 只关64/65+15%", "stopgrid-X7SafeStopHonoredNo6465"),
  # dry-run 窗口对齐验证：20260830-20261017，服务器同款 universe（static pairlist + 真实黑名单）
  ("[对齐] 现状", "stopgrid-parity-X7SafeStopHonored"),
  ("[对齐] 只关64/65", "stopgrid-parity-X7SafeStopHonoredNo6465"),
  ("[对齐] 关61-65", "stopgrid-parity-X7SafeStopHonoredNoRebuy"),
]


def trade_stats(run_dir: str) -> dict:
  stats = next(iter(json.loads(Path(_result_json(run_dir)).read_text(encoding="utf-8"))["strategy"].values()))
  trades = stats["trades"]
  rebuy = [t for t in trades if set((t["enter_tag"] or "").split()) & REBUY_TAGS]
  stops = [t for t in trades if t["exit_reason"] == "stop_loss"]
  wins = sum(t["profit_abs"] for t in trades if t["profit_abs"] > 0)
  losses = -sum(t["profit_abs"] for t in trades if t["profit_abs"] < 0)
  return {
    "winrate": 100.0 * sum(t["profit_abs"] > 0 for t in trades) / len(trades) if trades else 0.0,
    "pf": wins / losses if losses else float("inf"),
    "stops": len(stops),
    "stops_abs": sum(t["profit_abs"] for t in stops),
    "rebuy_n": len(rebuy),
    "rebuy_abs": sum(t["profit_abs"] for t in rebuy),
  }


def main() -> int:
  print(
    f"{'变体':24s}{'收益':>9s}{'回撤':>8s}{'收/撤':>7s}{'Sharpe':>8s}{'H1撤':>7s}{'H2撤':>7s}"
    f"{'笔数':>6s}{'胜率':>7s}{'PF':>6s}{'硬止损':>12s}{'rebuy':>14s}"
  )
  print("-" * 118)
  for label, run_dir in RUNS:
    if _result_json(run_dir) is None:
      print(f"[skip] {label} - no result yet ({run_dir})")
      continue
    m = analyse(run_dir)
    t = trade_stats(run_dir)
    print(
      f"{label:24s}{m['ret']:8.2f}%{m['dd']:7.2f}%{m['ratio']:7.1f}{m['sharpe']:8.2f}"
      f"{m['dd_h1']:6.2f}%{m['dd_h2']:6.2f}%{m['trades']:6d}{t['winrate']:6.1f}%{t['pf']:6.2f}"
      f"{t['stops']:5d}/{t['stops_abs']:6.0f}{t['rebuy_n']:6d}/{t['rebuy_abs']:7.0f}"
    )
  print("\n硬止损、rebuy 两列为 笔数/净盈亏(USDT)。回撤为逐日盯市口径，与 eval_grid.py 相同。")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
