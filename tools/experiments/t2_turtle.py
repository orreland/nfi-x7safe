"""reports/T2_TURTLE_2026-11-09.md: daily turtle simulator (T2), plus T1 in the same engine as a check.

Run from the repo root with PYTHONUTF8=1:  python tools/experiments/t2_turtle.py
Signals use the day's close and fill at the next day's open; only stops fill intraday.
"""
import sys
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

sys.path.insert(0, "user_data/strategies_trend")
from TrendDonchian import LOOKBACKS, donchian_state  # noqa: E402

DATA = "user_data/data_long/binance"
COINS = ["BTC", "ETH", "XRP", "SOL", "DOGE", "ADA", "TRX", "LINK", "AVAX", "DOT", "BCH", "LTC", "SHIB", "UNI"]
GROUP = {"BTC": 0, "ETH": 0, "XRP": 1, "SOL": 1, "ADA": 1, "TRX": 1, "LINK": 1, "AVAX": 1, "DOT": 1,
         "BCH": 2, "LTC": 2, "DOGE": 2, "SHIB": 2, "UNI": 2}
WINDOWS = {"L": ("2025-02-16", "2026-11-02"), "R": ("2026-08-30", "2026-11-02"), "W5": ("2021-01-01", "2026-11-02")}
C0 = 10_000.0


def load():
  d = {}
  for c in COINS:
    x = pd.read_feather(f"{DATA}/{c}_USDT-1d.feather").set_index("date").sort_index()
    x.index = x.index.tz_convert(None).normalize()
    d[c] = x[["open", "high", "low", "close", "volume"]].astype(float)
  return d


def indicators(x):
  pc = x["close"].shift(1)
  tr = pd.concat([x["high"], pc], axis=1).max(axis=1) - pd.concat([x["low"], pc], axis=1).min(axis=1)
  return pd.DataFrame({
    "N": tr.rolling(20, min_periods=20).mean(),
    "hi20": x["high"].shift(1).rolling(20, min_periods=20).max(), "hi55": x["high"].shift(1).rolling(55, min_periods=55).max(),
    "lo10": x["low"].shift(1).rolling(10, min_periods=10).min(), "lo20": x["low"].shift(1).rolling(20, min_periods=20).min(),
    "age": np.arange(1, len(x) + 1),
  }, index=x.index)


def hypo_s1(x, ind):
  """Background S1 trades on every 20-day breakout. Returns, per signal day, whether the last finished one won."""
  last_win = pd.Series(False, index=x.index)
  win, active, pending_in, pending_out = False, False, False, False
  entry = stop = 0.0
  o, h, l, c = (x[k].values for k in ("open", "high", "low", "close"))
  N, hi20, lo10 = ind["N"].values, ind["hi20"].values, ind["lo10"].values
  for i in range(len(x)):
    if pending_out:
      win, active, pending_out = o[i] > entry, False, False
    if pending_in:
      entry, stop, active, pending_in = o[i], o[i] - 2 * N[i - 1], True, False
    if active and l[i] <= stop:
      win, active = min(o[i], stop) > entry, False
    last_win.iloc[i] = win  # known at this close, before today's breakout starts a new one
    if active and c[i] < lo10[i]:
      pending_out = True
    if not active and not pending_in and not pending_out and np.isfinite(N[i]) and c[i] > hi20[i]:
      pending_in = True
  return last_win


@dataclass
class Pos:
  system: str
  qty: float = 0.0
  units: int = 0
  last_fill: float = 0.0
  last_N: float = 0.0
  stop: float = 0.0
  cost: float = 0.0  # cash paid incl. fees
  opened: object = None


@dataclass
class Book:
  cash: float = C0
  pos: dict = field(default_factory=dict)
  trades: list = field(default_factory=list)

  def buy(self, coin, qty, px, fee, slip):
    fill = px * (1 + slip)
    paid = qty * fill * (1 + fee)
    self.cash -= paid
    return fill, paid

  def sell(self, coin, px, day, reason, fee, slip):
    p = self.pos.pop(coin)
    got = p.qty * px * (1 - slip) * (1 - fee)
    self.cash += got
    self.trades.append({"coin": coin, "system": p.system, "open": p.opened, "close": day, "units": p.units,
                        "pnl": got - p.cost, "ret": got / p.cost - 1, "reason": reason})


def run_t2(D, IND, HW, start, end, fee=0.001, slip=0.0005, weather=True, adds=True, skip=True, caps=True, ddscale=True,
           coins=None, group=GROUP, btc=None, allowed=None):
  days = pd.date_range(start, end, freq="D")
  coins = coins or COINS
  btc = D["BTC"]["close"] if btc is None else btc
  last = {c: D[c].index[-1] for c in coins}
  sunny = btc > btc.rolling(200, min_periods=200).mean()
  b = Book()
  eq, peak, pend_exit, pend_add, pend_new = [], C0, [], [], []
  for day in days:
    px = {c: D[c].loc[day] for c in coins if day in D[c].index}
    for c in [c for c in b.pos if c not in px and day > last[c]]:  # data ended: delisted, sell at its last close
      b.sell(c, D[c]["close"].iloc[-1], day, "delist", fee, slip)
    # equity at yesterday's close, for sizing
    e_prev = eq[-1][1] if eq else C0
    k = int((1 - e_prev / peak) // 0.10) if ddscale else 0
    size_eq = e_prev * 0.8 ** max(k, 0)

    def units_total():
      return sum(p.units for p in b.pos.values())

    def units_group(g):
      return sum(p.units for c, p in b.pos.items() if group[c] == g)

    def unit_qty(coin, N, fill_px):
      q = 0.01 * size_eq / (2 * N)
      cap = b.cash / (fill_px * (1 + slip) * (1 + fee))
      q = min(q, cap)
      return q if q * fill_px >= 10 else 0.0

    # open: gap stops, then trend exits
    for c in list(b.pos):
      if c in px and px[c]["open"] <= b.pos[c].stop:
        b.sell(c, px[c]["open"], day, "stop", fee, slip)
    for c in pend_exit:
      if c in b.pos and c in px:
        b.sell(c, px[c]["open"], day, "trend", fee, slip)
    # adds
    for c, N in pend_add:
      p = b.pos.get(c)
      if p is None or c not in px or p.units >= 4:
        continue
      if caps and ((group is not None and units_group(group[c]) >= 6) or units_total() >= 10):
        continue
      q = unit_qty(c, N, px[c]["open"])
      if q <= 0:
        continue
      fill, paid = b.buy(c, q, px[c]["open"], fee, slip)
      p.qty += q; p.units += 1; p.cost += paid; p.last_fill, p.last_N = fill, N; p.stop = fill - 2 * N
    # new entries
    for c, system, N in pend_new:
      if c in b.pos or c not in px:
        continue
      if caps and ((group is not None and units_group(group[c]) >= 6) or units_total() >= 10):
        continue
      q = unit_qty(c, N, px[c]["open"])
      if q <= 0:
        continue
      fill, paid = b.buy(c, q, px[c]["open"], fee, slip)
      b.pos[c] = Pos(system, q, 1, fill, N, fill - 2 * N, paid, day)
    # intraday stops
    for c in list(b.pos):
      if c in px and px[c]["low"] <= b.pos[c].stop:
        b.sell(c, b.pos[c].stop, day, "stop", fee, slip)
    # close: mark to market, then tomorrow's orders
    value = b.cash + sum(p.qty * px[c]["close"] for c, p in b.pos.items() if c in px)
    eq.append((day, value))
    peak = max(peak, value)
    pend_exit, pend_add, pend_new = [], [], []
    ok_weather = bool(sunny.get(day, False)) if weather else True
    for c in coins:
      if c not in px:
        continue
      i, x = IND[c].loc[day], px[c]
      p = b.pos.get(c)
      if p is not None:
        if x["close"] < (i["lo10"] if p.system == "S1" else i["lo20"]):
          pend_exit.append(c)
        elif adds and ok_weather and p.units < 4 and x["close"] >= p.last_fill + 0.5 * p.last_N and np.isfinite(i["N"]):
          pend_add.append(((x["close"] - p.last_fill) / i["N"], c, i["N"]))
        continue
      if not ok_weather or i["age"] < 365 or not np.isfinite(i["N"]) or i["N"] <= 0 or (allowed and not allowed(c, day)):
        continue
      s1 = x["close"] > i["hi20"] and not (skip and bool(HW[c].loc[day]))
      s2 = x["close"] > i["hi55"]
      if s1:
        pend_new.append(((x["close"] - i["hi20"]) / i["N"], c, "S1", i["N"]))
      elif s2:
        pend_new.append(((x["close"] - i["hi55"]) / i["N"], c, "S2", i["N"]))
    pend_add = [(c, N) for _, c, N in sorted(pend_add, reverse=True)]
    pend_new = [(c, s, N) for _, c, s, N in sorted(pend_new, reverse=True)]
  for c, p in b.pos.items():  # still open at the end: counted as trades, valued at the last close after costs
    got = p.qty * D[c]["close"].loc[:day].iloc[-1] * (1 - slip) * (1 - fee)
    b.trades.append({"coin": c, "system": p.system, "open": p.opened, "close": day, "units": p.units, "pnl": got - p.cost, "ret": got / p.cost - 1, "reason": "open_at_end"})
  return pd.Series(dict(eq)), pd.DataFrame(b.trades), sunny


def run_t1(D, start, end, fee=0.001, coins=None, allowed=None):
  """T1 as Freqtrade runs it: 130 warm-up candles, whitelist order, stake = (open stakes + free) * weight, -30% stop."""
  coins = coins or COINS
  last = {c: D[c].index[-1] for c in coins}
  days = pd.date_range(start, end, freq="D")
  warm = pd.Timestamp(start) - pd.Timedelta(days=130)
  sig = {}
  for c in coins:
    x = D[c].loc[warm:end]
    score = sum(donchian_state(x["close"].values, x["high"].values, x["low"].values, n) for n in LOOKBACKS)
    vol = x["close"].pct_change().rolling(60).std() * np.sqrt(365)
    # Freqtrade drops the first 130 loaded candles of every pair, so a pair listed after the warm-up start trades 130 days later
    sig[c] = pd.DataFrame({"score": score, "vol": vol, "volume": x["volume"], "ready": np.arange(len(x)) >= 130}, index=x.index)
  cash, pos, trades, eq = C0, {}, [], []
  pend_in, pend_out = [], []
  for day in days:
    px = {c: D[c].loc[day] for c in coins if day in D[c].index}
    for c in [c for c in pos if c not in px and day > last[c]]:  # delisted: sell at the last close
      q, stake, o, od = pos.pop(c); got = q * D[c]["close"].iloc[-1] * (1 - fee)
      cash += got; trades.append({"coin": c, "open": od, "close": day, "stake": stake, "pnl": got - stake * (1 + fee), "ret": got / (stake * (1 + fee)) - 1, "reason": "delist"})
    for c in pend_out:
      if c in pos and c in px:
        q, stake, o, od = pos.pop(c)
        got = q * px[c]["open"] * (1 - fee)
        cash += got; trades.append({"coin": c, "open": od, "close": day, "stake": stake, "pnl": got - stake * (1 + fee), "ret": got / (stake * (1 + fee)) - 1, "reason": "exit"})
    for c, w in pend_in:
      if c in pos or c not in px or len(pos) >= 14:
        continue
      open_stakes = sum(p[1] for p in pos.values())
      stake = min((open_stakes + cash) * w, (open_stakes + cash) * 0.99 - open_stakes)
      if stake < 10:
        continue
      o = px[c]["open"]
      pos[c] = (stake / o, stake, o, day); cash -= stake * (1 + fee)
    for c in list(pos):
      q, stake, o, od = pos[c]
      if c in px and px[c]["low"] <= o * 0.7:
        fill = min(px[c]["open"], o * 0.7)
        pos.pop(c); got = q * fill * (1 - fee)
        cash += got; trades.append({"coin": c, "open": od, "close": day, "stake": stake, "pnl": got - stake * (1 + fee), "ret": got / (stake * (1 + fee)) - 1, "reason": "stop"})
    eq.append((day, cash + sum(p[0] * px[c]["close"] for c, p in pos.items() if c in px)))
    pend_in, pend_out = [], []
    for c in coins:
      if day not in sig[c].index or not sig[c].at[day, "ready"]:
        continue
      s = sig[c].loc[day]
      if c in pos and s["score"] == 0:
        pend_out.append(c)
      elif c not in pos and s["score"] >= 2 and s["volume"] > 0 and (allowed is None or allowed(c, day)):
        v = s["vol"]
        pend_in.append((c, 0.20 if not np.isfinite(v) or v <= 0 else min(0.20, 0.10 / v)))
  for c, (q, stake, o, od) in pos.items():  # Freqtrade force-exits at the last close; equity stays marked to market
    got = q * D[c]["close"].loc[:day].iloc[-1] * (1 - fee)
    trades.append({"coin": c, "open": od, "close": day, "stake": stake, "pnl": got - stake * (1 + fee), "ret": got / (stake * (1 + fee)) - 1, "reason": "open_at_end"})
  return pd.Series(dict(eq)), pd.DataFrame(trades)


def stats(eq, tr):
  ret = eq.iloc[-1] / C0 - 1
  e = pd.concat([pd.Series([C0], index=[eq.index[0] - pd.Timedelta(days=1)]), eq])
  dd = float(-(e / e.cummax() - 1).min())
  yrs = (eq.index[-1] - eq.index[0]).days / 365 + 1 / 365
  ann = (1 + ret) ** (1 / yrs) - 1
  n = len(tr)
  return {"ret": ret * 100, "dd": dd * 100, "ann": ann * 100, "ann_dd": ann / dd if dd else np.nan, "ret_dd": ret / dd if dd else np.nan,
          "n": n, "win": 100 * (tr["pnl"] > 0).mean() if n else np.nan, "pf": tr.loc[tr.pnl > 0, "pnl"].sum() / -tr.loc[tr.pnl < 0, "pnl"].sum() if n and (tr.pnl < 0).any() else np.nan}


def fmt(s):
  return f"ret {s['ret']:+8.2f}%  dd {s['dd']:6.2f}%  ann {s['ann']:+7.2f}%  ann/dd {s['ann_dd']:5.2f}  ret/dd {s['ret_dd']:6.2f}  n {s['n']:4d}  win {s['win']:5.1f}%  pf {s['pf']:.2f}"


def bh(D, start, end):
  x = D["BTC"].loc[start:end]
  eq = x["close"] / x["open"].iloc[0] * C0
  return stats(eq, pd.DataFrame({"pnl": []}))


if __name__ == "__main__":
  D = load()
  IND = {c: indicators(D[c]) for c in COINS}
  HW = {c: hypo_s1(D[c], IND[c]) for c in COINS}
  FT = {"L": -6.34, "R": -2.04, "W5": 568.53}
  print("=== 1.3 engine check: T1 in this engine vs Freqtrade")
  T1 = {}
  for w, (a, z) in WINDOWS.items():
    eq, tr = run_t1(D, a, z)
    T1[w] = stats(eq, tr)
    gap = T1[w]["ret"] - FT[w]
    lim = 3.0 if w != "W5" else 0.15 * FT[w]
    print(f"T1 {w:3s} {fmt(T1[w])} | Freqtrade {FT[w]:+.2f}%  gap {gap:+.2f}  {'ok' if abs(gap) <= lim else 'NO'}")

  print("\n=== T2")
  T2, EQ = {}, {}
  for w, (a, z) in WINDOWS.items():
    eq, tr, sunny = run_t2(D, IND, HW, a, z)
    T2[w], EQ[w] = stats(eq, tr), (eq, tr, sunny)
    print(f"T2 {w:3s} {fmt(T2[w])}")
  for w, (a, z) in WINDOWS.items():
    print(f"BTC hold {w:3s} {fmt(bh(D, a, z))}")
  eq2, tr2, _ = run_t2(D, IND, HW, *WINDOWS["W5"], fee=0.002, slip=0.001)
  cost2 = stats(eq2, tr2)
  print(f"T2 W5 double cost {fmt(cost2)}")

  L, R, W = T2["L"], T2["R"], T2["W5"]
  btc_w = bh(D, *WINDOWS["W5"])
  checks = [
    ("1 L ret>0 & ret/dd>=1", f"{L['ret']:+.2f}% / {L['ret_dd']:.2f}", L["ret"] > 0 and L["ret_dd"] >= 1.0),
    ("2 L dd<=20%", f"{L['dd']:.2f}%", L["dd"] <= 20),
    ("3 R ret>=T1 R", f"{R['ret']:+.2f}% vs {T1['R']['ret']:+.2f}%", R["ret"] >= T1["R"]["ret"]),
    ("4 W5 dd<=35%", f"{W['dd']:.2f}%", W["dd"] <= 35),
    ("5 W5 ann/dd>=T1 & BTC", f"{W['ann_dd']:.2f} vs T1 {T1['W5']['ann_dd']:.2f}, BTC {btc_w['ann_dd']:.2f}", W["ann_dd"] >= T1["W5"]["ann_dd"] and W["ann_dd"] >= btc_w["ann_dd"]),
    ("6 W5 n>=100", f"{W['n']}", W["n"] >= 100),
    ("7 W5 double cost ret>0", f"{cost2['ret']:+.2f}%", cost2["ret"] > 0),
  ]
  print("\n=== 1.4 verdict:", "PASS" if all(c[2] for c in checks) else "FAIL")
  for name, val, ok in checks:
    print(f"  {name:26s} {val:40s} {'ok' if ok else 'NO'}")

  print("\n=== 1.5 info only")
  eq, tr, sunny = EQ["W5"]
  ye = pd.concat([pd.Series([C0], index=[eq.index[0] - pd.Timedelta(days=1)]), eq])
  for y in range(2021, 2027):
    e = ye[(ye.index >= f"{y - 1}-12-31") & (ye.index <= f"{y}-12-31")]
    print(f"  W5 {y}: ret {(e.iloc[-1] / e.iloc[0] - 1) * 100:+7.2f}%  dd {-(e / e.cummax() - 1).min() * 100:5.2f}%  end {e.iloc[-1]:9.0f}")
  dpnl = ye.diff().dropna()
  sun = sunny.reindex(dpnl.index).fillna(False).astype(bool)
  print(f"  W5 sunny days {sun.sum()} pnl {dpnl[sun].sum():+.0f} | cloudy days {(~sun).sum()} pnl {dpnl[~sun].sum():+.0f}")
  print(f"  W5 by system: " + ", ".join(f"{s} n={len(g)} pnl {g.pnl.sum():+.0f} win {100 * (g.pnl > 0).mean():.0f}%" for s, g in tr.groupby("system")))
  print(f"  W5 by exit: " + ", ".join(f"{s} n={len(g)} pnl {g.pnl.sum():+.0f}" for s, g in tr.groupby("reason")))
  print(f"  W5 units per trade: " + ", ".join(f"{u}: {len(g)} (pnl {g.pnl.sum():+.0f})" for u, g in tr.groupby("units")))
  print(f"  W5 best 5 trades: " + ", ".join(f"{r.coin} {r.open:%Y-%m} {r.pnl:+.0f}" for r in tr.nlargest(5, 'pnl').itertuples()))
  for name, kw in (("no weather", {"weather": False}), ("no adds", {"adds": False}), ("no skip", {"skip": False}),
                   ("no caps", {"caps": False}), ("no ddscale", {"ddscale": False})):
    line = []
    for w, (a, z) in WINDOWS.items():
      s = stats(*run_t2(D, IND, HW, a, z, **kw)[:2])
      line.append(f"{w} {s['ret']:+.1f}%/{s['dd']:.1f}% ({s['ann_dd']:.2f}, n{s['n']})")
    print(f"  ablation {name:11s} " + "  ".join(line))
