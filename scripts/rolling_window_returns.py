#!/usr/bin/env python
"""rolling_window_returns.py - how unusual is a given short-window result?

Rebuilds each run's mark-to-market daily equity (same method as eval_grid.py)
and reports the distribution of rolling N-day returns, so a dry-run window can
be placed against the backtest's own history ("is -4.5% over 48 days a normal
bad stretch or something the backtest never showed?").

USAGE
  .venv\\Scripts\\python.exe scripts\\rolling_window_returns.py --days 48 --threshold -4.5 \\
      stopgrid-X7SafeStopHonored stopgrid-X7SafeStopHonoredNo6465
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_grid import _result_json  # noqa: E402
from nfi_backtest_lib import USER_DATA, _rebuild_equity_curve  # noqa: E402


def main() -> int:
  ap = argparse.ArgumentParser()
  ap.add_argument("runs", nargs="+")
  ap.add_argument("--days", type=int, default=48)
  ap.add_argument("--threshold", type=float, default=-4.5, help="percent")
  a = ap.parse_args()

  print(f"rolling {a.days}-day return (%), mark-to-market daily equity")
  print(f"{'run':40s}{'min':>8s}{'p5':>8s}{'p25':>8s}{'median':>8s}{'<0':>8s}{f'<={a.threshold}':>9s}  worst window")
  for run in a.runs:
    path = _result_json(run)
    if path is None:
      print(f"[skip] {run}")
      continue
    stats = next(iter(json.loads(Path(path).read_text(encoding="utf-8"))["strategy"].values()))
    eq = _rebuild_equity_curve(stats, USER_DATA / "data" / "binance")
    r = (eq / eq.shift(a.days) - 1).dropna() * 100
    worst = r.idxmin()
    print(
      f"{run:40s}{r.min():8.2f}{r.quantile(0.05):8.2f}{r.quantile(0.25):8.2f}{r.median():8.2f}"
      f"{(r < 0).mean() * 100:7.1f}%{(r <= a.threshold).mean() * 100:8.1f}%  "
      f"{(worst - pd.Timedelta(days=a.days)):%Y-%m-%d}..{worst:%Y-%m-%d}"
    )
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
