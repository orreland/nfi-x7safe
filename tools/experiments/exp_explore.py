"""Exploratory, not a pre-registered check: stop outliers and where the arms differ over time."""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "scripts")
from export_baselines import load_stats  # noqa: E402
from nfi_backtest_lib import USER_DATA, _rebuild_equity_curve  # noqa: E402

REB = {"61", "62", "63", "64", "65", "68"}
for run in ("comm-L-OURS", "exp-X8S-comm-L"):
  tr = load_stats(run)["trades"]
  off = []
  for t in tr:
    tags = (t["enter_tag"] or "").split()
    reb = tags and all(c in REB | {"120"} for c in tags) and any(c in REB for c in tags)
    want = 0.85 if reb else 0.75
    r = t["stop_loss_abs"] / t["orders"][0]["safe_price"]
    if abs(r - want) > 0.01:
      off.append((t["pair"], t["open_date"][:10], t["enter_tag"].strip(), round(r, 3), len(t["orders"]), t["exit_reason"][:26], round(t["profit_abs"])))
  print(run, "off", len(off), "of", len(tr))
  for o in off[:14]:
    print("  ", o)

curves = {}
for label, run in (("OURS", "comm-L-OURS"), ("OURS-S", "exp-OURS-S-comm-L"), ("X8", "comm-L-X8"), ("X8S", "exp-X8S-comm-L"), ("X8S-S", "exp-X8S-S-comm-L"), ("X8N", "exp-X8N-comm-L")):
  eq = _rebuild_equity_curve(load_stats(run), USER_DATA / "data" / "binance")
  curves[label] = eq
  dd = eq / eq.cummax() - 1
  t = dd.idxmin()
  print(f"{label:7s} max dd {dd.min() * 100:.2f}% on {str(t)[:10]}, peak {str(eq.loc[:t].idxmax())[:10]}")
df = pd.DataFrame(curves)
q = df.resample("QE").last()
print("\nquarter return %")
print(q.pct_change().fillna(q.iloc[0] / 10000 - 1).mul(100).round(1).to_string())

print("\nlosers by delisted-at-end? X8S vs OURS biggest losses")
for run in ("comm-L-OURS", "exp-X8S-comm-L", "exp-X8N-comm-L"):
  tr = sorted(load_stats(run)["trades"], key=lambda t: t["profit_abs"])[:5]
  print(run, [(t["pair"], t["open_date"][:10], t["exit_reason"][:20], round(t["profit_abs"])) for t in tr])
