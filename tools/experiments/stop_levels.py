"""Final stop price / first entry price, by side, for one run (median and range)."""
import glob
import json
import statistics
import sys

REBUY = {"61", "62", "63", "64", "65", "68"}
GRIND = {"120"}


def is_rebuy(tag):
    t = (tag or "").split()
    return bool(t) and (all(c in REBUY for c in t) or (any(c in REBUY for c in t) and all(c in REBUY | GRIND for c in t)))


for run in sys.argv[1:]:
    p = [f for f in glob.glob(f"D:/NostalgiaForInfinity/user_data/backtest_results/{run}/backtest-result-*.json")
         if "_config" not in f and "meta" not in f][0]
    trades = next(iter(json.load(open(p, encoding="utf-8"))["strategy"].values()))["trades"]
    out = []
    for side, pred in (("rebuy", is_rebuy), ("other", lambda t: not is_rebuy(t))):
        r = []
        for t in trades:
            if not pred(t["enter_tag"]):
                continue
            first = next((o["safe_price"] for o in t["orders"] if o.get("ft_is_entry")), t["open_rate"])
            r.append(t["stop_loss_abs"] / first)
        if r:
            out.append(f"{side}: n={len(r)} min={min(r):.3f} median={statistics.median(r):.3f} max={max(r):.3f}")
    print(f"{run:42s} " + " | ".join(out))
