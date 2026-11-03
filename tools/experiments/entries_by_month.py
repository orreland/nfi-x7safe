"""Trades opened per month in a backtest result (to spot entry droughts)."""
import collections
import glob
import json
import sys

for run in sys.argv[1:]:
    p = [f for f in glob.glob(f"D:/NostalgiaForInfinity/user_data/backtest_results/{run}/backtest-result-*.json")
         if "_config" not in f and "meta" not in f][0]
    s = next(iter(json.load(open(p, encoding="utf-8"))["strategy"].values()))
    c = collections.Counter(t["open_date"][:7] for t in s["trades"])
    print(f"== {run}")
    print("   " + "  ".join(f"{m}:{c[m]}" for m in sorted(c)))
    gl = [lk for lk in s.get("locks", []) if lk.get("pair") == "*"]
    for lk in gl:
        print(f"   GLOBAL LOCK {lk['lock_time']} -> {lk['lock_end_time']}  active={lk.get('active')}  {lk.get('reason', '')[:60]}")
