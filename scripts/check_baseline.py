#!/usr/bin/env python
"""Compare a re-run with its published baseline, trade by trade.
Usage: check_baseline.py run [run...]. Exit code 0 only if every run matches."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_baselines import OUT, load_stats, rows  # noqa: E402

ABS_TOL = 0.01  # USDT, rounding only


def check(run: str) -> bool:
  with open(OUT / f"{run}.trades.csv", newline="", encoding="utf-8") as f:
    want = list(csv.reader(f))[1:]
  got = rows(load_stats(run))
  diffs = [(w, g) for w, g in zip(want, got) if w[:5] != g[:5] or abs(float(w[6]) - float(g[6])) > ABS_TOL]
  ok = len(want) == len(got) and not diffs
  print(f"{'PASS' if ok else 'FAIL'} {run}: baseline {len(want)} trades, re-run {len(got)}, {len(diffs)} differ")
  for w, g in diffs[:5]:
    print(f"  want {w}\n  got  {g}")
  return ok


if __name__ == "__main__":
  raise SystemExit(0 if all([check(r) for r in sys.argv[1:]]) else 1)
