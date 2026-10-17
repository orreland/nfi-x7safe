#!/usr/bin/env python
"""compare_parity.py - does the backtest reproduce what the dry-run actually did?

Matches every closed dry-run trade to a backtest trade on the same pair whose
open time is within --tolerance minutes, then reports:
  - how many dry-run trades the backtest also took (and vice versa)
  - P&L of matched / dry-run-only / backtest-only trades
  - for matched trades, exit reason and profit side by side

A backtest that is profitable over the dry-run window while the dry-run lost is
only useful once this says WHERE the two diverge: different entries (signal /
universe / fill model) or same entries with different exits (stop handling).

USAGE
  .venv\\Scripts\\python.exe scripts\\compare_parity.py stopgrid-parity-X7SafeStopHonored \\
      --db dryrun_backups/nfi-dryrun-20261017.sqlite
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_grid import _result_json  # noqa: E402


def load_backtest(run_dir: str) -> pd.DataFrame:
  path = _result_json(run_dir)
  if path is None:
    raise SystemExit(f"no result for {run_dir}")
  stats = next(iter(json.loads(Path(path).read_text(encoding="utf-8"))["strategy"].values()))
  df = pd.DataFrame(stats["trades"])
  df["open_date"] = pd.to_datetime(df["open_date"], utc=True)
  return df[["pair", "open_date", "enter_tag", "exit_reason", "profit_ratio", "profit_abs"]]


def load_dryrun(db: str) -> pd.DataFrame:
  con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
  df = pd.read_sql(
    "select pair, open_date, enter_tag, exit_reason, close_profit as profit_ratio, close_profit_abs as profit_abs"
    " from trades where is_open=0",
    con,
  )
  df["open_date"] = pd.to_datetime(df["open_date"], utc=True, format="ISO8601")
  return df


def pf(s: pd.Series) -> str:
  loss = -s[s < 0].sum()
  return f"{s[s > 0].sum() / loss:.2f}" if loss else "inf"


def summary(label: str, df: pd.DataFrame) -> None:
  if df.empty:
    print(f"{label:14s} n=  0")
    return
  w = (df.profit_abs > 0).sum()
  print(f"{label:14s} n={len(df):3d}  W/L={w}/{len(df) - w}  net={df.profit_abs.sum():9.2f} USDT  PF={pf(df.profit_abs)}")


def main() -> int:
  ap = argparse.ArgumentParser()
  ap.add_argument("run_dir")
  ap.add_argument("--db", default="dryrun_backups/nfi-dryrun-20261017.sqlite")
  ap.add_argument("--tolerance", type=int, default=60, help="minutes")
  a = ap.parse_args()

  bt, dr = load_backtest(a.run_dir), load_dryrun(a.db)
  tol = pd.Timedelta(minutes=a.tolerance)
  used: set[int] = set()
  pairs = []
  for i, d in dr.iterrows():
    cand = bt[(bt.pair == d.pair) & ((bt.open_date - d.open_date).abs() <= tol) & ~bt.index.isin(used)]
    if len(cand):
      j = (cand.open_date - d.open_date).abs().idxmin()
      used.add(j)
      pairs.append((i, j))

  m_dr = dr.loc[[i for i, _ in pairs]]
  m_bt = bt.loc[[j for _, j in pairs]]
  print(f"== {a.run_dir}  vs  {a.db}  (match: same pair, open within {a.tolerance} min)")
  summary("dry-run all", dr)
  summary("backtest all", bt)
  print()
  summary("matched (dr)", m_dr)
  summary("matched (bt)", m_bt)
  summary("dry-run only", dr.drop(m_dr.index))
  summary("backtest only", bt.drop(m_bt.index))

  print("\n-- matched trades: pair | open(dr) | tag | dr exit / % | bt exit / %")
  for i, j in sorted(pairs, key=lambda p: dr.loc[p[0], "profit_ratio"]):
    d, b = dr.loc[i], bt.loc[j]
    print(
      f"{d.pair:12s} {d.open_date:%m-%d %H:%M} {str(d.enter_tag).strip():6s} "
      f"{str(d.exit_reason)[:30]:30s} {d.profit_ratio * 100:7.2f} | {str(b.exit_reason)[:30]:30s} {b.profit_ratio * 100:7.2f}"
    )

  print("\n-- dry-run losers NOT in backtest:")
  for _, d in dr.drop(m_dr.index).sort_values("profit_ratio").iterrows():
    if d.profit_abs < 0:
      print(f"{d.pair:12s} {d.open_date:%m-%d %H:%M} {str(d.enter_tag).strip():6s} {str(d.exit_reason)[:30]:30s} {d.profit_ratio * 100:7.2f}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
