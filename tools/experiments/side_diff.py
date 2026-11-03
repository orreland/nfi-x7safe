"""List trades of one side (rebuy / other) that both runs took but closed differently.

usage: side_diff.py <base_run> <new_run> rebuy|other
Expected for an arm that leaves that side untouched: only stake-size knock-ons
(same exit reason and close time, profit within a few thousandths of a percent).
"""
import glob
import json
import sys

REBUY = {"61", "62", "63", "64", "65", "68"}
GRIND = {"120"}


def load(run):
    p = [f for f in glob.glob(f"D:/NostalgiaForInfinity/user_data/backtest_results/{run}/backtest-result-*.json")
         if "_config" not in f and "meta" not in f][0]
    return {(t["pair"], t["open_date"]): t for t in next(iter(json.load(open(p, encoding="utf-8"))["strategy"].values()))["trades"]}


def is_rebuy(tag):
    t = (tag or "").split()
    return bool(t) and (all(c in REBUY for c in t) or (any(c in REBUY for c in t) and all(c in REBUY | GRIND for c in t)))


a, b, side = load(sys.argv[1]), load(sys.argv[2]), sys.argv[3]
want = (lambda t: is_rebuy(t)) if side == "rebuy" else (lambda t: not is_rebuy(t))
both = [k for k in set(a) & set(b) if want(a[k]["enter_tag"])]
rows = [k for k in both if (a[k]["exit_reason"], a[k]["close_date"]) != (b[k]["exit_reason"], b[k]["close_date"])
        or abs(a[k]["profit_ratio"] - b[k]["profit_ratio"]) > 1e-6]
exit_diff = [k for k in rows if (a[k]["exit_reason"], a[k]["close_date"]) != (b[k]["exit_reason"], b[k]["close_date"])]
max_pdiff = max((abs(a[k]["profit_ratio"] - b[k]["profit_ratio"]) * 100 for k in rows), default=0.0)
print(f"[{side}] same entry in both: {len(both)}  closed differently: {len(rows)}  "
      f"of which exit reason/time differs: {len(exit_diff)}  max profit diff: {max_pdiff:.4f}pp")
for k in sorted(exit_diff)[:15]:
    x, y = a[k], b[k]
    print(f"  {k[0]:11s} {k[1][:16]}  {x['exit_reason'][:26]:26s} {x['profit_ratio'] * 100:7.2f}% | "
          f"{y['exit_reason'][:26]:26s} {y['profit_ratio'] * 100:7.2f}%")
