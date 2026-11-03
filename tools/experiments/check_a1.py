"""Sanity-check X7SafeRebuyStop25 against X7SafeStopHonored on the same window.

Expectations:
  - non-rebuy trades: identical exits wherever both runs took the same trade
  - every hard-stop exit: close ~= first entry price x 0.85 (non-rebuy) / 0.75 (rebuy),
    or below it when the candle opened through the stop
"""
import glob
import json
import sys

REBUY = {"61", "62", "63", "64", "65", "68"}
GRIND = {"120"}


def load(run):
    p = [f for f in glob.glob(f"D:/NostalgiaForInfinity/user_data/backtest_results/{run}/backtest-result-*.json")
         if "_config" not in f and "meta" not in f][0]
    return next(iter(json.load(open(p, encoding="utf-8"))["strategy"].values()))["trades"]


def is_rebuy(tag):
    t = (tag or "").split()
    return bool(t) and (all(c in REBUY for c in t) or (any(c in REBUY for c in t) and all(c in REBUY | GRIND for c in t)))


def first_price(tr):
    entries = [o for o in tr["orders"] if o.get("ft_is_entry")]
    return entries[0]["safe_price"] if entries else tr["open_rate"]


base_run, new_run = sys.argv[1], sys.argv[2]
base = {(t["pair"], t["open_date"]): t for t in load(base_run)}
new = {(t["pair"], t["open_date"]): t for t in load(new_run)}
same = set(base) & set(new)
diff_nonrebuy = [k for k in same if not is_rebuy(base[k]["enter_tag"]) and
                 (base[k]["exit_reason"] != new[k]["exit_reason"] or abs(base[k]["profit_ratio"] - new[k]["profit_ratio"]) > 1e-6)]
print(f"{base_run}: {len(base)}  {new_run}: {len(new)}  same entries: {len(same)}")
print(f"non-rebuy trades in both with different exit: {len(diff_nonrebuy)}")
for k in diff_nonrebuy[:10]:
    print("  ", k, base[k]["exit_reason"], round(base[k]["profit_ratio"] * 100, 2), "->", new[k]["exit_reason"], round(new[k]["profit_ratio"] * 100, 2))

for name, trades in (("BASE", base), ("NEW", new)):
    print(f"\n-- {name} hard-stop / doom exits: pair | rebuy | n_entries | close/first | profit%")
    for t in sorted(trades.values(), key=lambda x: x["open_date"]):
        if t["exit_reason"] in ("stop_loss", "trailing_stop_loss") or "doom" in t["exit_reason"]:
            n_entries = sum(1 for o in t["orders"] if o.get("ft_is_entry"))
            print(f"  {t['pair']:12s} {str(is_rebuy(t['enter_tag'])):5s} {n_entries:2d}  {t['close_rate'] / first_price(t):.4f}  "
                  f"{t['profit_ratio'] * 100:7.2f}  {t['exit_reason'][:34]}")
