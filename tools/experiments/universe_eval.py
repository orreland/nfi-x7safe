"""Evaluate reports/UNIVERSE_VOLUME_2026-11-06.md. Run from the repo root with PYTHONUTF8=1."""
import glob
import json
import re
import sys
import zipfile
from pathlib import Path

import numpy as np

sys.path.insert(0, "scripts")
from eval_grid import _dd, _result_json  # noqa: E402
from nfi_backtest_lib import USER_DATA, _rebuild_equity_curve  # noqa: E402

RES = Path("user_data/backtest_results")
RUNS = {"M": "entry-M", "S14": "univ-S14", "V20": "univ-V20", "V40": "univ-V40", "V40T": "univ-V40T"}
if "sweep" in sys.argv:  # reports/UNIVERSE_SWEEP_2026-11-07.md
  RUNS = {"M": "entry-M", **{f"V{n}": f"univ-V{n}" for n in (20, 30, 40, 50, 60, 80)}}


def load(run):
  for z in glob.glob(str(RES / run / "backtest-result-*.zip")):
    with zipfile.ZipFile(z) as f:
      for n in f.namelist():
        if not (RES / run / n).exists():
          f.extract(n, RES / run)
  stats = next(iter(json.loads(Path(_result_json(run)).read_text(encoding="utf-8"))["strategy"].values()))
  eq = _rebuild_equity_curve(stats, USER_DATA / "data" / "binance")
  tr = stats["trades"]
  w = sum(t["profit_abs"] for t in tr if t["profit_abs"] > 0)
  l = -sum(t["profit_abs"] for t in tr if t["profit_abs"] < 0)
  monthly = eq.resample("ME").last().pct_change().fillna(eq.resample("ME").last().iloc[0] / eq.iloc[0] - 1) * 100
  under, longest, peak = 0, 0, -np.inf
  for v in eq.values:
    peak = max(peak, v)
    under = under + 1 if v < peak else 0
    longest = max(longest, under)
  sel = lambda f: [t for t in tr if f(t["exit_reason"])]
  doom, hard = sel(lambda r: "doom" in r), sel(lambda r: r in ("stop_loss", "stoploss_on_exchange"))
  log = Path(f"logs_univ_{run.split('-', 1)[1]}.log") if run.startswith("univ") else None
  m = re.findall(r"UNIVERSE table \((\d+), (\d+)\), mean allowed per day ([\d.]+)", log.read_text(encoding="utf-8", errors="ignore")) if log and log.exists() else []
  return {
    "ret": (eq.iloc[-1] / eq.iloc[0] - 1) * 100, "dd": _dd(eq), "n": len(tr), "pf": w / l if l else float("inf"),
    "win": 100 * np.mean([t["profit_abs"] > 0 for t in tr]) if tr else 0, "worst_m": monthly.min(), "worst_m_at": f"{monthly.idxmin():%Y-%m}",
    "under_d": longest, "doom": f"{len(doom)}/{sum(t['profit_abs'] for t in doom):.0f}", "hard": f"{len(hard)}/{sum(t['profit_abs'] for t in hard):.0f}",
    "pairs": f"{m[-1][1]} ranked, {float(m[-1][2]):.1f}/day" if m else "-", "traded": len({t["pair"] for t in tr}),
    "recon": abs(eq.iloc[-1] - stats["final_balance"]) / stats["final_balance"] * 100,
    **{f"y{y}": _year(eq, y) for y in ("2025", "2026")},
  }


def _year(eq, y):
  e = eq.loc[f"{int(y) - 1}-12-31":f"{y}-12-31"] if y != "2025" else eq.loc[:"2025-12-31"]
  if len(e) < 3:
    return (float("nan"), float("nan"), float("nan"))
  r, d = (e.iloc[-1] / e.iloc[0] - 1) * 100, _dd(e)
  return (r, d, r / d if d else float("nan"))


R = {(a, w): load(f"{r}-{w}") for a, r in RUNS.items() for w in "LR"}
print(f"{'arm':5s}{'win':4s}{'ret%':>9s}{'dd%':>7s}{'ratio':>7s}{'PF':>6s}{'n':>5s}{'win%':>6s}{'worstM%':>9s}{'at':>8s}{'under_d':>8s}{'doom':>10s}{'hard':>10s}{'coins':>6s}  universe")
for (a, w), s in R.items():
  ratio = s["ret"] / s["dd"] if s["dd"] else float("nan")
  print(f"{a:5s}{w:4s}{s['ret']:9.2f}{s['dd']:7.2f}{ratio:7.2f}{s['pf']:6.2f}{s['n']:5d}{s['win']:6.1f}{s['worst_m']:9.2f}{s['worst_m_at']:>8s}"
        f"{s['under_d']:8d}{s['doom']:>10s}{s['hard']:>10s}{s['traded']:6d}  {s['pairs']}  recon_err={s['recon']:.3f}%")

ml, mr = R["M", "L"], R["M", "R"]
mratio = ml["ret"] / ml["dd"]
print(f"\nPre-registered criteria (M: L {ml['ret']:.2f}/{ml['dd']:.2f}/{mratio:.2f}, R {mr['ret']:.2f})")
for a in list(RUNS)[1:]:
  l, r = R[a, "L"], R[a, "R"]
  ratio = l["ret"] / l["dd"] if l["dd"] else float("nan")
  checks = [
    ("dd<=0.8M", l["dd"], 0.8 * ml["dd"], l["dd"] <= 0.8 * ml["dd"]),
    ("ratio>=M", ratio, mratio, ratio >= mratio),
    ("ret>=0.5M", l["ret"], 0.5 * ml["ret"], l["ret"] >= 0.5 * ml["ret"]),
    ("R>=M+2", r["ret"], mr["ret"] + 2, r["ret"] >= mr["ret"] + 2),
    ("n>=100", l["n"], 100, l["n"] >= 100),
  ]
  verdict = "SAMPLE TOO SMALL" if l["n"] < 100 else ("PASS" if all(c[3] for c in checks) else "FAIL")
  print(f"{a:5s}{verdict:17s}" + "  ".join(f"{c[0]} {c[1]:.2f}/{c[2]:.2f} {'ok' if c[3] else 'NO'}" for c in checks))

if "sweep" in sys.argv:
  print("\nStep 2: yearly ratio vs M (L window)")
  passed = []
  for a in list(RUNS)[1:]:
    l, r = R[a, "L"], R[a, "R"]
    ratio = l["ret"] / l["dd"]
    step1 = l["dd"] <= 0.8 * ml["dd"] and ratio >= mratio and l["ret"] >= 0.5 * ml["ret"] and r["ret"] >= mr["ret"] + 2 and l["n"] >= 100
    yrs = all(l[k][2] >= ml[k][2] for k in ("y2025", "y2026"))
    print(f"{a:5s} step1={'ok' if step1 else 'NO'} 2025 {l['y2025'][0]:+.1f}/{l['y2025'][1]:.2f}={l['y2025'][2]:.2f} (M {ml['y2025'][2]:.2f})"
          f"  2026 {l['y2026'][0]:+.1f}/{l['y2026'][1]:.2f}={l['y2026'][2]:.2f} (M {ml['y2026'][2]:.2f})  years={'ok' if yrs else 'NO'}")
    if step1 and yrs:
      passed.append((ratio, a))
  print("candidate:", max(passed)[1] if passed else "none", "| all passing step 1+2:", [a for _, a in sorted(passed, reverse=True)])
