"""Does the 1m fill model reproduce real dry-run first-entry prices? Run from the repo root."""
import sqlite3
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "scripts")
sys.path.insert(0, "user_data/strategies")
from entry_model import market_at_order, minutes  # noqa: E402
from export_baselines import load_stats  # noqa: E402

bt = pd.DataFrame(load_stats("comm-R-OURS")["trades"])
bt["od"] = pd.to_datetime(bt.open_date, utc=True)
c = sqlite3.connect("file:dryrun_backups/nfi-dryrun-20261103.sqlite?mode=ro", uri=True)
q = """select t.pair,trim(t.enter_tag) tag,t.open_date,
 (select coalesce(o.average,o.price) from orders o where o.ft_trade_id=t.id and o.ft_order_side='buy' and o.status='closed' order by o.id limit 1) p
 from trades t where t.open_date>='2026-08-30'"""
dr = pd.read_sql(q, c)
dr["od"] = pd.to_datetime(dr.open_date, utc=True, format="ISO8601")
rows, miss = [], 0
for _, d in dr.iterrows():
  k = bt[(bt.pair == d.pair) & ((bt.od - d.od).abs() <= pd.Timedelta(minutes=15))]
  if not len(k):
    continue
  t = k.iloc[0]
  bars = minutes(d.pair, t.od.to_pydatetime())
  if bars is None:
    miss += 1
    continue
  o = float(bars["o"].iloc[0])
  rows.append(dict(pair=d.pair, tag=d.tag, secs=(d.od - t.od).total_seconds(), real=d.p / o - 1, model=market_at_order(bars) / o - 1, c0=float(bars["c"].iloc[0]) / o - 1,
                   low3=float(bars["l"].iloc[1:].min()) / o - 1))
m = pd.DataFrame(rows)
print("matched", len(m), "no 1m data", miss)
print("real  mean %.4f median %.4f" % (m.real.mean(), m.real.median()))
print("model mean %.4f median %.4f corr %.3f" % (m.model.mean(), m.model.median(), m.real.corr(m.model)))
print("c0    mean %.4f corr %.3f" % (m.c0.mean(), m.real.corr(m.c0)))
print("abs err mean %.4f; real-model mean %.4f" % ((m.real - m.model).abs().mean(), (m.real - m.model).mean()))
print("secs mean %.0f min %.0f max %.0f; corr(secs, real) %.3f" % (m.secs.mean(), m.secs.min(), m.secs.max(), m.secs.corr(m.real)))
print("low of next 3 min vs open: mean %.4f; share below open %.2f, below -0.25%% %.2f, below -0.5%% %.2f" % (m.low3.mean(), (m.low3 < 0).mean(), (m.low3 < -0.0025).mean(), (m.low3 < -0.005).mean()))
reb = m.tag.str.match(r"^6[1-8]$")
print("rebuy real %.4f model %.4f | normal real %.4f model %.4f" % (m.real[reb].mean(), m.model[reb].mean(), m.real[~reb].mean(), m.model[~reb].mean()))
