#!/usr/bin/env python
"""Write reports/baselines/<run>.trades.csv and metrics.csv from backtest results,
so a re-run can be compared trade by trade. Usage: export_baselines.py run [run...]"""

from __future__ import annotations

import csv
import json
import sys
import zipfile
from glob import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "baselines"
COLS = ["pair", "open_date", "close_date", "enter_tag", "exit_reason", "profit_ratio", "profit_abs"]


def load_stats(run: str) -> dict:
  """The strategy block of a run's newest result, read straight from its zip."""
  zips = sorted(glob(str(ROOT / "user_data" / "backtest_results" / run / "backtest-result-*.zip")))
  if not zips:
    raise SystemExit(f"no result zip for {run}")
  with zipfile.ZipFile(zips[-1]) as z:
    name = next(n for n in z.namelist() if n.endswith(".json") and "_config" not in n and "meta" not in n)
    return next(iter(json.loads(z.read(name))["strategy"].values()))


def rows(stats: dict) -> list[list[str]]:
  return [
    [
      t["pair"],
      t["open_date"][:19],
      t["close_date"][:19],
      (t["enter_tag"] or "").strip(),
      t["exit_reason"],
      f"{t['profit_ratio']:.6f}",
      f"{t['profit_abs']:.4f}",
    ]
    for t in stats["trades"]
  ]


def main() -> int:
  OUT.mkdir(parents=True, exist_ok=True)
  metrics = []
  for run in sys.argv[1:]:
    s = load_stats(run)
    r = rows(s)
    with open(OUT / f"{run}.trades.csv", "w", newline="", encoding="utf-8") as f:
      w = csv.writer(f, lineterminator="\n")
      w.writerow(COLS)
      w.writerows(r)
    metrics.append(
      [
        run,
        len(r),
        f"{s['final_balance']:.4f}",
        f"{s['profit_total'] * 100:.4f}",
        f"{s['max_relative_drawdown'] * 100:.4f}",
        f"{s.get('market_change', 0) * 100:.2f}",
      ]
    )
  with open(OUT / "metrics.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["run", "trades", "final_balance", "profit_total_pct", "max_relative_drawdown_pct", "market_change_pct"])
    w.writerows(metrics)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
