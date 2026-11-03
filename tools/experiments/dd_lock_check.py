"""Recompute, for every MaxDrawdown global lock in a run, both drawdown measures
over the trades closed in the 24h lookback before the lock:

  ratios : drawdown of the cumulative sum of per-trade close_profit (freqtrade default)
  equity : relative drawdown of realized USDT equity, starting from
           starting_balance (10000 x 0.85) + profit realized before the window

Mirrors freqtrade's MaxDrawdown (trade_limit 10, lookback 288 x 5m) and
calculate_max_drawdown's _calc_drawdown_series closely enough to check which
mode a lock is consistent with.
"""
import glob
import json
import sys
from datetime import datetime, timedelta

START = 10000 * 0.85
LOOKBACK = timedelta(minutes=288 * 5)


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)


def dd_series(values, start):
    cum, high, worst = start, start, 0.0
    for v in values:
        cum += v
        high = max(high, cum)
        if high > 0:
            worst = max(worst, (high - cum) / high)
    return worst


def ratio_dd(values):
    cum, high, worst = 0.0, 0.0, 0.0
    for v in values:
        cum += v
        high = max(high, cum)
        worst = max(worst, high - cum)
    return worst


for run in sys.argv[1:]:
    p = [f for f in glob.glob(f"D:/NostalgiaForInfinity/user_data/backtest_results/{run}/backtest-result-*.json")
         if "_config" not in f and "meta" not in f][0]
    s = next(iter(json.load(open(p, encoding="utf-8"))["strategy"].values()))
    trades = sorted(s["trades"], key=lambda t: t["close_date"])
    locks = [lk for lk in s.get("locks", []) if lk.get("pair") == "*"]
    print(f"== {run}: {len(locks)} MaxDrawdown global lock(s)")
    for lk in locks:
        now = ts(lk["lock_time"])
        win = [t for t in trades if now - LOOKBACK < ts(t["close_date"]) <= now]
        before = sum(t["profit_abs"] for t in trades if ts(t["close_date"]) <= now - LOOKBACK)
        r = ratio_dd([t["profit_ratio"] for t in win])
        e = dd_series([t["profit_abs"] for t in win], START + before)
        print(f"   {lk['lock_time'][:16]}  trades in window={len(win):3d}  ratios-dd={r * 100:6.2f}%  equity-dd={e * 100:6.2f}%"
              f"  | reported: {lk['reason'][:28]}")
