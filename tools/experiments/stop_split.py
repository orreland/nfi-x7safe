"""Hard-stop exits split by rebuy / non-rebuy, per run."""
import glob
import json
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
    for label, pred in (("rebuy", is_rebuy), ("other", lambda t: not is_rebuy(t))):
        st = [t for t in trades if t["exit_reason"] in ("stop_loss", "trailing_stop_loss") and pred(t["enter_tag"])]
        allp = [t for t in trades if pred(t["enter_tag"])]
        out.append(f"{label}: stops {len(st):3d} / {sum(t['profit_abs'] for t in st):8.0f}  all {len(allp):3d} / {sum(t['profit_abs'] for t in allp):8.0f}")
    print(f"{run:40s} " + " | ".join(out))
