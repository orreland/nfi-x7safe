"""List non-rebuy trades that both runs took but closed differently (reason / close time / profit)."""
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


a, b = load(sys.argv[1]), load(sys.argv[2])
rows = []
for k in set(a) & set(b):
    x, y = a[k], b[k]
    if is_rebuy(x["enter_tag"]):
        continue
    if (x["exit_reason"], x["close_date"]) != (y["exit_reason"], y["close_date"]) or abs(x["profit_ratio"] - y["profit_ratio"]) > 1e-6:
        rows.append((k, x, y))
print(f"non-rebuy, same entry, different close: {len(rows)}")
for k, x, y in sorted(rows):
    same_exit = (x["exit_reason"], x["close_date"]) == (y["exit_reason"], y["close_date"])
    print(f"  {k[0]:11s} {k[1][:16]}  {'same exit/time' if same_exit else 'EXIT DIFFERS'}  "
          f"{x['exit_reason'][:24]:24s} {x['profit_ratio'] * 100:7.3f}% {x['stake_amount']:8.1f} | "
          f"{y['exit_reason'][:24]:24s} {y['profit_ratio'] * 100:7.3f}% {y['stake_amount']:8.1f}")
