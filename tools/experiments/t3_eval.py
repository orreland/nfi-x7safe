"""reports/T3_NEWCOINS_2026-11-09.md: T3 (T2 without adds) on coins never used for trend tests.

Run tools/experiments/t3_data.py first, then this, from the repo root with PYTHONUTF8=1.
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, "tools/experiments")
import t2_turtle as t  # noqa: E402

CACHE = Path("user_data/data_t3")


def load_new():
  """One series per coin; a hole longer than 3 days means the old coin ended (LUNA 2022), the rest is a new coin."""
  D, segs = {}, {}
  for f in sorted(CACHE.glob("*_USDT-1d.feather")):
    coin = f.name.split("_USDT")[0]
    x = pd.read_feather(f).set_index("date").sort_index()
    x.index = pd.DatetimeIndex(x.index).normalize()
    x = x[["open", "high", "low", "close", "volume"]].astype(float)
    cut = [0] + [i for i, g in enumerate(x.index.to_series().diff().dt.days) if g > 3] + [len(x)]
    for k in range(len(cut) - 1):
      name = coin if k == 0 else f"{coin}{k + 1}"
      D[name] = x.iloc[cut[k]:cut[k + 1]]
      segs.setdefault(coin, []).append(name)
  return D, segs


def lists(D, segs):
  uni = {int(y): v for y, v in json.loads((CACHE / "universe.json").read_text()).items()}
  out = {}
  for y, coins in uni.items():
    pick = set()
    for c in coins:
      live = [s for s in segs[c] if D[s].index[0] <= pd.Timestamp(f"{y - 1}-12-31") <= D[s].index[-1]]
      pick.add(live[0] if live else segs[c][-1])
    out[y] = pick
  return out


if __name__ == "__main__":
  D, segs = load_new()
  U = lists(D, segs)
  print("split coins:", {c: s for c, s in segs.items() if len(s) > 1})
  print("2022 list has", sorted(c for c in U[2022] if c.startswith("LUNA")), "| 2026 list has", sorted(c for c in U[2026] if c.startswith("LUNA")))
  coins = sorted({c for v in U.values() for c in v})
  D14 = t.load()
  btc = D14["BTC"]["close"]
  IND = {c: t.indicators(D[c]) for c in coins}
  HW = {c: t.hypo_s1(D[c], IND[c]) for c in coins}
  allowed = lambda c, day: c in U.get(day.year, ())
  kw = dict(coins=coins, group=None, btc=btc, allowed=allowed)

  R = {}
  for w, (a, z) in t.WINDOWS.items():
    R["T3", w] = t.run_t2(D, IND, HW, a, z, adds=False, **kw)[:2]
    R["T2", w] = t.run_t2(D, IND, HW, a, z, adds=True, **kw)[:2]
    R["T3 no weather", w] = t.run_t2(D, IND, HW, a, z, adds=False, weather=False, **kw)[:2]
    R["T1", w] = t.run_t1(D, a, z, coins=coins, allowed=allowed)
  S = {k: t.stats(*v) for k, v in R.items()}
  print("\n=== new coins")
  for arm in ("T3", "T1", "T2", "T3 no weather"):
    for w in t.WINDOWS:
      print(f"{arm:14s} {w:3s} {t.fmt(S[arm, w])}")
  B = {w: t.bh(D14, a, z) for w, (a, z) in t.WINDOWS.items()}
  for w in t.WINDOWS:
    print(f"{'BTC hold':14s} {w:3s} {t.fmt(B[w])}")
  c2 = t.stats(*t.run_t2(D, IND, HW, *t.WINDOWS["W5"], adds=False, fee=0.002, slip=0.001, **kw)[:2])
  print(f"{'T3 2x cost':14s} W5  {t.fmt(c2)}")

  L, Rw, W, T1 = S["T3", "L"], S["T3", "R"], S["T3", "W5"], {w: S["T1", w] for w in t.WINDOWS}
  checks = [
    ("1 L ret>0 & ret/dd>=1", f"{L['ret']:+.2f}% / {L['ret_dd']:.2f}", L["ret"] > 0 and L["ret_dd"] >= 1.0),
    ("2 L dd<=20%", f"{L['dd']:.2f}%", L["dd"] <= 20),
    ("3 R ret>=T1 R", f"{Rw['ret']:+.2f}% vs {T1['R']['ret']:+.2f}%", Rw["ret"] >= T1["R"]["ret"]),
    ("4 W5 dd<=35%", f"{W['dd']:.2f}%", W["dd"] <= 35),
    ("5 W5 ann/dd>=T1 & BTC", f"{W['ann_dd']:.2f} vs T1 {T1['W5']['ann_dd']:.2f}, BTC {B['W5']['ann_dd']:.2f}", W["ann_dd"] >= T1["W5"]["ann_dd"] and W["ann_dd"] >= B["W5"]["ann_dd"]),
    ("6 W5 n>=100", f"{W['n']}", W["n"] >= 100),
    ("7 W5 double cost ret>0", f"{c2['ret']:+.2f}%", c2["ret"] > 0),
  ]
  print("\n=== 1.4 verdict:", "PASS" if all(c[2] for c in checks) else "FAIL")
  for name, val, ok in checks:
    print(f"  {name:26s} {val:40s} {'ok' if ok else 'NO'}")
  print(f"\nA: T3 W5 ann/dd {W['ann_dd']:.2f} vs T2 {S['T2', 'W5']['ann_dd']:.2f} -> {'T3 higher' if W['ann_dd'] > S['T2', 'W5']['ann_dd'] else 'T3 NOT higher'}")
  print(f"B: T3 W5 ann/dd {W['ann_dd']:.2f} vs no weather {S['T3 no weather', 'W5']['ann_dd']:.2f} -> {'T3 higher' if W['ann_dd'] > S['T3 no weather', 'W5']['ann_dd'] else 'T3 NOT higher'}")

  print("\n=== info")
  IND14 = {c: t.indicators(D14[c]) for c in t.COINS}
  HW14 = {c: t.hypo_s1(D14[c], IND14[c]) for c in t.COINS}
  for w, (a, z) in t.WINDOWS.items():
    print(f"reference: T3 on the old 14 coins {w:3s} {t.fmt(t.stats(*t.run_t2(D14, IND14, HW14, a, z, adds=False)[:2]))}")
  eq, tr = R["T3", "W5"]
  ye = pd.concat([pd.Series([t.C0], index=[eq.index[0] - pd.Timedelta(days=1)]), eq])
  for y in range(2021, 2027):
    e = ye[(ye.index >= f"{y - 1}-12-31") & (ye.index <= f"{y}-12-31")]
    print(f"  T3 W5 {y}: ret {(e.iloc[-1] / e.iloc[0] - 1) * 100:+7.2f}%  dd {-(e / e.cummax() - 1).min() * 100:5.2f}%  end {e.iloc[-1]:9.0f}")
  eq1, _ = R["T1", "W5"]
  ye1 = pd.concat([pd.Series([t.C0], index=[eq1.index[0] - pd.Timedelta(days=1)]), eq1])
  print("  T1 W5 year-end:", " ".join(f"{y}:{ye1[ye1.index <= f'{y}-12-31'].iloc[-1]:.0f}" for y in range(2021, 2027)))
  print("  T3 W5 by exit:", ", ".join(f"{s} n={len(g)} pnl {g.pnl.sum():+.0f}" for s, g in tr.groupby("reason")))
  print("  T3 W5 by system:", ", ".join(f"{s} n={len(g)} pnl {g.pnl.sum():+.0f} win {100 * (g.pnl > 0).mean():.0f}%" for s, g in tr.groupby("system")))
  print(f"  T3 W5 coins traded {tr.coin.nunique()}; best:", ", ".join(f"{r.coin} {r.open:%Y-%m} {r.pnl:+.0f}" for r in tr.nlargest(5, "pnl").itertuples()))
  print("  T3 W5 worst:", ", ".join(f"{r.coin} {r.open:%Y-%m} {r.pnl:+.0f} ({r.reason})" for r in tr.nsmallest(5, "pnl").itertuples()))
  top = tr.nlargest(3, "pnl").pnl.sum()
  print(f"  T3 W5 total pnl {tr.pnl.sum():+.0f}; without the best 3 trades {tr.pnl.sum() - top:+.0f}")
