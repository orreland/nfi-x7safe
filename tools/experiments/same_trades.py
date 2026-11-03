"""Are two backtest results trade-for-trade identical?"""
import glob
import json
import sys


def load(run):
    p = [f for f in glob.glob(f"D:/NostalgiaForInfinity/user_data/backtest_results/{run}/backtest-result-*.json")
         if "_config" not in f and "meta" not in f][0]
    s = next(iter(json.load(open(p, encoding="utf-8"))["strategy"].values()))
    return [(t["pair"], t["open_date"], t["close_date"], t["exit_reason"], round(t["profit_abs"], 8)) for t in s["trades"]], s


a, sa = load(sys.argv[1])
b, sb = load(sys.argv[2])
print(sys.argv[1], len(a), round(sa["profit_total_abs"], 6))
print(sys.argv[2], len(b), round(sb["profit_total_abs"], 6))
print("IDENTICAL" if a == b else f"DIFFERENT: {len(set(a) ^ set(b))} trades differ")
