"""Evaluate reports/ENTRY_POLICY_2026-11-04.md. Run from the repo root with PYTHONUTF8=1."""
import glob
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path[:0] = ["scripts", "user_data/strategies"]
from entry_model import decide  # noqa: E402
from eval_grid import analyse  # noqa: E402
from export_baselines import load_stats  # noqa: E402

RES = Path("user_data/backtest_results")
ARMS = {"M": None, "C25": 0.0025, "L0": 0.0, "L25": -0.0025, "L50": -0.005}


def unzip(run):
  for z in glob.glob(str(RES / run / "backtest-result-*.zip")):
    with zipfile.ZipFile(z) as f:
      for n in f.namelist():
        if not (RES / run / n).exists():
          f.extract(n, RES / run)


def load(arm, win):
  run = f"entry-{arm}-{win}"
  unzip(run)
  m = analyse(run)
  tr = load_stats(run)["trades"]
  w = sum(t["profit_abs"] for t in tr if t["profit_abs"] > 0)
  l = -sum(t["profit_abs"] for t in tr if t["profit_abs"] < 0)
  doom = [t for t in tr if "doom" in t["exit_reason"]]
  hard = [t for t in tr if t["exit_reason"] in ("stop_loss", "stoploss_on_exchange")]
  return {
    "ret": m["ret"], "dd": m["dd"], "ratio": m["ratio"], "pf": w / l if l else float("inf"), "n": len(tr),
    "win": 100 * np.mean([t["profit_abs"] > 0 for t in tr]), "doom": len(doom), "doom_abs": sum(t["profit_abs"] for t in doom),
    "hard": len(hard), "hard_abs": sum(t["profit_abs"] for t in hard), "tr": tr,
  }


R = {(a, w): load(a, w) for a in ARMS for w in "LR"}
print(f"{'arm':6s}{'win':4s}{'ret%':>9s}{'dd%':>7s}{'ratio':>7s}{'PF':>6s}{'n':>5s}{'win%':>6s}{'doom':>11s}{'hard':>11s}")
for (a, w), s in R.items():
  print(f"{a:6s}{w:4s}{s['ret']:9.2f}{s['dd']:7.2f}{s['ratio']:7.2f}{s['pf']:6.2f}{s['n']:5d}{s['win']:6.1f}"
        f"{s['doom']:5d}/{s['doom_abs']:5.0f}{s['hard']:5d}/{s['hard_abs']:5.0f}")

print("\nPre-registered criteria against M")
ml, mr = R["M", "L"], R["M", "R"]
for a in list(ARMS)[1:]:
  l, r = R[a, "L"], R[a, "R"]
  checks = [
    ("ratio>=1.1M", l["ratio"], 1.1 * ml["ratio"], l["ratio"] >= 1.1 * ml["ratio"]),
    ("dd<=M+0.5", l["dd"], ml["dd"] + 0.5, l["dd"] <= ml["dd"] + 0.5),
    ("ret>=0.9M", l["ret"], 0.9 * ml["ret"], l["ret"] >= 0.9 * ml["ret"]),
    ("R>=M-0.5", r["ret"], mr["ret"] - 0.5, r["ret"] >= mr["ret"] - 0.5),
    ("n>=0.6M", l["n"], 0.6 * ml["n"], l["n"] >= 0.6 * ml["n"]),
  ]
  print(f"{a:4s} {'PASS' if all(c[3] for c in checks) else 'FAIL'}  " + "  ".join(f"{c[0]} {c[1]:.2f}/{c[2]:.2f} {'ok' if c[3] else 'NO'}" for c in checks))

print("\nReplaying each policy on M's own first entries (profit as it was in M)")
for w in "LR":
  rows = [(t["pair"], pd.Timestamp(t["open_date"]).to_pydatetime(), t["profit_abs"], t["profit_ratio"], t["exit_reason"]) for t in R["M", w]["tr"]]
  for a, off in list(ARMS.items())[1:]:
    d = [decide(p, when, off) for p, when, *_ in rows]
    skip = [r for r, x in zip(rows, d) if x is None]
    kept = [r for r, x in zip(rows, d) if x is not None and x != "nodata"]
    nodata = sum(x == "nodata" for x in d)
    f = lambda rs: f"n={len(rs):4d} sum={sum(r[2] for r in rs):8.0f} mean={100 * np.mean([r[3] for r in rs]) if rs else 0:6.2f}% win={100 * np.mean([r[2] > 0 for r in rs]) if rs else 0:5.1f}% doom={sum('doom' in r[4] for r in rs)}"
    print(f"{w} {a:4s} skip {100 * len(skip) / len(rows):5.1f}%  skipped {f(skip)} | kept {f(kept)} | nodata={nodata}")

print("\nActual trade overlap with M (pair + open time)")
for w in "LR":
  key = lambda t: (t["pair"], t["open_date"])
  base = {key(t): t for t in R["M", w]["tr"]}
  for a in list(ARMS)[1:]:
    arm = {key(t): t for t in R[a, w]["tr"]}
    both = base.keys() & arm.keys()
    gone = sum(base[k]["profit_abs"] for k in base.keys() - arm.keys())
    new = sum(arm[k]["profit_abs"] for k in arm.keys() - base.keys())
    same = sum(arm[k]["profit_abs"] - base[k]["profit_abs"] for k in both)
    print(f"{w} {a:4s} same={len(both):4d} delta={same:8.0f} | only in M={len(base) - len(both):4d} sum={gone:8.0f} | only in arm={len(arm) - len(both):4d} sum={new:8.0f}")
