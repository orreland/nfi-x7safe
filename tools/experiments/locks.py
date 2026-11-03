"""Protection locks recorded in a backtest result, grouped by reason."""
import collections
import glob
import json
import sys

for run in sys.argv[1:]:
    p = [f for f in glob.glob(f"D:/NostalgiaForInfinity/user_data/backtest_results/{run}/backtest-result-*.json")
         if "_config" not in f and "meta" not in f][0]
    s = next(iter(json.load(open(p, encoding="utf-8"))["strategy"].values()))
    locks = s.get("locks", [])
    c = collections.Counter()
    examples = {}
    for lk in locks:
        reason = (lk.get("reason") or "").split(" ")[0] + " " + ("GLOBAL" if lk.get("pair") == "*" else "pair")
        c[reason] += 1
        examples.setdefault(reason, f"{lk.get('pair')} {lk.get('lock_time')} -> {lk.get('lock_end_time')} | {lk.get('reason')}")
    print(f"== {run}: {len(locks)} locks")
    for r, n in c.most_common():
        print(f"   {n:4d}  {r:30s} e.g. {examples[r][:150]}")
