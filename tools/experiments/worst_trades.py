"""Worst single trades (USDT and %) per run, plus non-rebuy exit-mechanism breakdown."""
import collections
import glob
import json
import sys

REBUY = {"61", "62", "63", "64", "65", "68"}
GRIND = {"120"}


def is_rebuy(tag):
    t = (tag or "").split()
    return bool(t) and (all(c in REBUY for c in t) or (any(c in REBUY for c in t) and all(c in REBUY | GRIND for c in t)))


def kind(reason):
    if reason in ("stop_loss", "trailing_stop_loss"):
        return "hard_stop"
    if "doom" in reason:
        return "doom"
    if "time_stop" in reason:
        return "time_stop"
    if reason == "force_exit":
        return "force_exit"
    return "signal"


for run in sys.argv[1:]:
    p = [f for f in glob.glob(f"D:/NostalgiaForInfinity/user_data/backtest_results/{run}/backtest-result-*.json")
         if "_config" not in f and "meta" not in f][0]
    trades = next(iter(json.load(open(p, encoding="utf-8"))["strategy"].values()))["trades"]
    worst = sorted(trades, key=lambda t: t["profit_abs"])[:3]
    w = " ; ".join(f"{t['pair']} {t['profit_abs']:.0f} ({t['profit_ratio'] * 100:.1f}%, {t['exit_reason'][:22]})" for t in worst)
    agg = collections.defaultdict(lambda: [0, 0.0])
    for t in trades:
        if not is_rebuy(t["enter_tag"]) and t["profit_abs"] < 0:
            k = kind(t["exit_reason"])
            agg[k][0] += 1
            agg[k][1] += t["profit_abs"]
    a = ", ".join(f"{k} {n}/{v:.0f}" for k, (n, v) in sorted(agg.items()))
    print(f"{run:36s} worst: {w}\n{'':36s} non-rebuy losers by mechanism: {a}")
