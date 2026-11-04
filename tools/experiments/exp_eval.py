"""Evaluate reports/EXPERIMENTS_2026-11-03.md. Run from the repo root with PYTHONUTF8=1."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "scripts")
from eval_grid import _dd, _result_json, analyse  # noqa: E402
from export_baselines import load_stats  # noqa: E402
from nfi_backtest_lib import USER_DATA, _rebuild_equity_curve  # noqa: E402

RES = Path("user_data/backtest_results")


def unzip(run):
  import glob
  import zipfile

  for z in glob.glob(str(RES / run / "backtest-result-*.zip")):
    with zipfile.ZipFile(z) as f:
      for n in f.namelist():
        if not (RES / run / n).exists():
          f.extract(n, RES / run)


def pf(tr):
  w = sum(t["profit_abs"] for t in tr if t["profit_abs"] > 0)
  l = -sum(t["profit_abs"] for t in tr if t["profit_abs"] < 0)
  return w / l if l else float("inf")


ARMS = [
  ("comm-L-OURS", "OURS comm-L"), ("exp-OURS-S-comm-L", "OURS-S comm-L"), ("comm-L-X8", "X8 comm-L"),
  ("exp-X8-S-comm-L", "X8-S comm-L"), ("exp-X8S-comm-L", "X8S comm-L"), ("exp-X8S-S-comm-L", "X8S-S comm-L"),
  ("exp-X8N-comm-L", "X8N comm-L"),
  ("comm-R-OURS", "OURS comm-R"), ("exp-OURS-S-comm-R", "OURS-S comm-R"), ("comm-R-X8", "X8 comm-R"),
  ("exp-X8-S-comm-R", "X8-S comm-R"), ("exp-X8S-comm-R", "X8S comm-R"), ("exp-X8S-S-comm-R", "X8S-S comm-R"),
  ("exp-X8N-comm-R", "X8N comm-R"),
  ("main-L-OURS", "OURS main-L"), ("exp-OURS-S-main-L", "OURS-S main-L"), ("main-L-X8", "X8 main-L"),
  ("exp-X8S-main-L", "X8S main-L"), ("exp-X8N-main-L", "X8N main-L"),
  ("main-R-OURS", "OURS main-R"), ("main-R-X8", "X8 main-R"), ("exp-X8S-main-R", "X8S main-R"),
]

print(f"{'arm':16s}{'ret%':>9s}{'dd%':>7s}{'ratio':>7s}{'sh':>6s}{'PF':>6s}{'n':>5s}{'win%':>6s}{'worst':>7s}{'doom':>12s}{'hard':>12s}{'time':>6s}{'force':>12s}{'maxd':>6s}")
M = {}
for run, label in ARMS:
  unzip(run)
  s = load_stats(run)
  tr = s["trades"]
  m = analyse(run)
  M[label] = m
  def cnt(f):
    x = [t for t in tr if f(t["exit_reason"])]
    return f"{len(x)}/{sum(t['profit_abs'] for t in x):.0f}"
  print(f"{label:16s}{m['ret']:9.2f}{m['dd']:7.2f}{m['ratio']:7.1f}{m['sharpe']:6.2f}{pf(tr):6.2f}{len(tr):5d}"
        f"{100 * np.mean([t['profit_abs'] > 0 for t in tr]):6.1f}{min(t['profit_abs'] for t in tr):7.0f}"
        f"{cnt(lambda r: 'doom' in r):>12s}{cnt(lambda r: r in ('stop_loss', 'stoploss_on_exchange')):>12s}"
        f"{sum(t['exit_reason'].startswith('exit_time_stop') for t in tr):6d}{cnt(lambda r: r == 'force_exit'):>12s}"
        f"{max(t['trade_duration'] for t in tr) / 1440:6.1f}")

print("\n-- X8 safety pre-checks")
REB = {"61", "62", "63", "64", "65", "68"}
for run in ("exp-X8S-comm-L", "exp-X8S-comm-R", "exp-X8S-main-L", "exp-X8N-comm-L", "exp-X8S-S-comm-L"):
  tr = load_stats(run)["trades"]
  # stop_loss_abs is the trade's final stop; trades that moved it after a DCA would show here.
  norm, reb = [], []
  for t in tr:
    tags = (t["enter_tag"] or "").split()
    r = t["stop_loss_abs"] / t["orders"][0]["safe_price"]
    (reb if tags and all(c in REB | {"120"} for c in tags) and any(c in REB for c in tags) else norm).append(r)
  q = lambda a: (round(float(np.median(a)), 3), round(float(np.min(a)), 3), round(float(np.max(a)), 3), round(float(np.mean(np.abs(np.array(a) - np.median(a)) > 0.01)), 3)) if a else None
  log = Path(f"logs_exp_{run[4:]}.log").read_text(encoding="utf-8", errors="replace")
  print(run, "normal(med,min,max,share off)", q(norm), "rebuy", q(reb), "ERR", log.count(" - ERROR - "), "Traceback", log.count("Traceback"))


def trend_curve(run):
  """Daily mark-to-market from 1d closes; T1 has no partial fills."""
  s = load_stats(run)
  closes = {}
  for p in {t["pair"] for t in s["trades"]}:
    d = pd.read_feather(f"user_data/data_long/binance/{p.replace('/', '_')}-1d.feather")
    closes[p] = d.set_index("date")["close"]
  start, end = pd.Timestamp(s["backtest_start"], tz="UTC").normalize(), pd.Timestamp(s["backtest_end"], tz="UTC").normalize()
  idx = pd.date_range(start, end, freq="D", tz="UTC")
  eq = pd.Series(10000.0, index=idx)
  for t in s["trades"]:
    o, c = pd.Timestamp(t["open_date"]), pd.Timestamp(t["close_date"])
    pnl = pd.Series(0.0, index=idx)
    pnl[idx >= c] = t["profit_abs"]
    px = closes[t["pair"]].reindex(idx).ffill()
    live = (idx >= o) & (idx < c)
    pnl[live] = (px[live] - t["open_rate"]) * t["amount"] - t["stake_amount"] * 0.001
    eq = eq + pnl
  return eq, s


def stats(eq):
  r = eq.pct_change().dropna()
  ret = (eq.iloc[-1] / eq.iloc[0] - 1) * 100
  dd = _dd(eq)
  return ret, dd, ret / dd if dd else float("nan"), r.mean() / r.std() * np.sqrt(365) if r.std() else float("nan")


print("\n-- Trend T1")
curves = {}
for w in ("L", "R", "W5"):
  run = f"exp-T1-{w}"
  unzip(run)
  eq, s = trend_curve(run)
  curves[w] = eq
  tr = s["trades"]
  print(w, "ret %.2f dd %.2f ratio %.2f sharpe %.2f" % stats(eq), "PF %.2f n %d win %.1f worst %.0f maxd %.0f ft_total %.2f ft_dd %.2f mkt %.1f exits %s" % (
    pf(tr), len(tr), 100 * np.mean([t["profit_abs"] > 0 for t in tr]), min(t["profit_abs"] for t in tr),
    max(t["trade_duration"] for t in tr) / 1440, s["profit_total"] * 100, s["max_relative_drawdown"] * 100, s["market_change"] * 100,
    pd.Series([t["exit_reason"] for t in tr]).value_counts().to_dict()))
  if w == "W5":
    print("   year end equity", {str(k.year): round(v) for k, v in eq.resample("YE").last().items()})
  btc = pd.read_feather("user_data/data_long/binance/BTC_USDT-1d.feather").set_index("date")["close"].reindex(eq.index).ffill()
  print("   BTC hold ret %.2f dd %.2f ratio %.2f sharpe %.2f" % stats(btc))

print("\n-- Blend")
base = _rebuild_equity_curve(load_stats("comm-L-OURS"), USER_DATA / "data" / "binance")
base.index = pd.DatetimeIndex(base.index).tz_convert("UTC").normalize() if pd.DatetimeIndex(base.index).tz is not None else pd.DatetimeIndex(base.index).tz_localize("UTC").normalize()
t = curves["L"]
idx = base.index.intersection(t.index)
ra, rb = base.loc[idx].pct_change().dropna(), t.loc[idx].pct_change().dropna()
print("days", len(idx), "corr %.3f" % ra.corr(rb))
blend = (1 + (ra + rb) / 2).cumprod() * 10000
print("OURS ret %.2f dd %.2f ratio %.2f sh %.2f" % stats(base.loc[idx]))
print("T1   ret %.2f dd %.2f ratio %.2f sh %.2f" % stats(t.loc[idx]))
print("50/50 ret %.2f dd %.2f ratio %.2f sh %.2f" % stats(blend))
print("down days of OURS: T1 mean %.4f OURS mean %.4f" % (rb[ra < 0].mean(), ra[ra < 0].mean()))
