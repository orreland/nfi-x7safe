"""Evaluate reports/ENTRY_RETRY_2026-11-08.md. Run from the repo root with PYTHONUTF8=1."""
import glob
import json
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "scripts")
from eval_grid import _dd, _result_json  # noqa: E402
from nfi_backtest_lib import USER_DATA, _rebuild_equity_curve  # noqa: E402

RES = Path("user_data/backtest_results")
RUNS = {"M": "entry-M", "V40": "univ-V40", "MR": "retry-MR", "V40R": "retry-V40R"}


def load(run):
  for z in glob.glob(str(RES / run / "backtest-result-*.zip")):
    with zipfile.ZipFile(z) as f:
      for n in f.namelist():
        if not (RES / run / n).exists():
          f.extract(n, RES / run)
  stats = next(iter(json.loads(Path(_result_json(run)).read_text(encoding="utf-8"))["strategy"].values()))
  eq = _rebuild_equity_curve(stats, USER_DATA / "data" / "binance")
  tr = pd.DataFrame(stats["trades"])
  tr["key"] = tr["pair"] + " " + pd.to_datetime(tr["open_date"], utc=True).dt.strftime("%Y-%m-%d %H:%M")
  return {"ret": (eq.iloc[-1] / eq.iloc[0] - 1) * 100, "dd": _dd(eq), "n": len(tr), "tr": tr,
          "recon": abs(eq.iloc[-1] - stats["final_balance"]) / stats["final_balance"] * 100}


def retried(run):
  log = Path(f"logs_retry_{run.split('-', 1)[1]}.log").read_text(encoding="utf-8", errors="ignore")
  return {f"{p} {d[:16]}": float(g) for p, d, g in re.findall(r"ENTRY-RETRY (\S+) (\S+ \S+) filled after retry at ([+-][\d.]+)", log)}


R = {(a, w): load(f"{r}-{w}") for a, r in RUNS.items() for w in "LR"}
print(f"{'arm':5s}{'win':4s}{'ret%':>9s}{'dd%':>7s}{'ratio':>7s}{'n':>5s}")
for (a, w), s in R.items():
  print(f"{a:5s}{w:4s}{s['ret']:9.2f}{s['dd']:7.2f}{s['ret'] / s['dd']:7.2f}{s['n']:5d}  recon_err={s['recon']:.3f}%")

print("\nQuestion 1: trades that only exist because of the retry")
for arm, base in (("MR", "M"), ("V40R", "V40")):
  for w in "LR":
    new, old = R[arm, w]["tr"], R[base, w]["tr"]
    rk = retried(f"{RUNS[arm]}-{w}")
    hit = new[new["key"].isin(rk)]
    added, gone = new[~new["key"].isin(old["key"])], old[~old["key"].isin(new["key"])]
    print(f"{arm}-{w}: retry fills logged {len(rk)}, of which opened a trade {len(hit)}: "
          f"sum {hit['profit_abs'].sum():+.0f} USDT, win {int((hit['profit_abs'] > 0).sum())}/{len(hit)}")
    for _, t in hit.iterrows():
      print(f"    {t['key']}  entry vs last close {rk[t['key']]:+.4f}  profit {t['profit_ratio'] * 100:+.2f}% {t['profit_abs']:+.1f} USDT  {t['exit_reason']}")
    print(f"  vs {base}: trades only in {arm} {len(added)} ({added['profit_abs'].sum():+.0f} USDT), only in {base} {len(gone)} "
          f"({gone['profit_abs'].sum():+.0f} USDT), common {len(new) - len(added)}; total profit {new['profit_abs'].sum():+.0f} vs {old['profit_abs'].sum():+.0f}")

ml, mr = R["MR", "L"], R["MR", "R"]
mratio = ml["ret"] / ml["dd"]
l, r = R["V40R", "L"], R["V40R", "R"]
ratio = l["ret"] / l["dd"]
checks = [
  ("dd<=0.8MR", l["dd"], 0.8 * ml["dd"], l["dd"] <= 0.8 * ml["dd"]),
  ("ratio>=MR", ratio, mratio, ratio >= mratio),
  ("ret>=0.5MR", l["ret"], 0.5 * ml["ret"], l["ret"] >= 0.5 * ml["ret"]),
  ("R>=MR+2", r["ret"], mr["ret"] + 2, r["ret"] >= mr["ret"] + 2),
  ("n>=100", l["n"], 100, l["n"] >= 100),
]
print(f"\nQuestion 2 (MR: L {ml['ret']:.2f}/{ml['dd']:.2f}/{mratio:.2f}, R {mr['ret']:.2f})")
print("V40R", "PASS" if all(c[3] for c in checks) else "FAIL", "  ".join(f"{c[0]} {c[1]:.2f}/{c[2]:.2f} {'ok' if c[3] else 'NO'}" for c in checks))
