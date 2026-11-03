"""Section-22 evaluation: rebuy half-size / rebuy -25% on the N25 + E10 base."""
import glob
import json
import sys

sys.path.insert(0, r"D:\NostalgiaForInfinity\scripts")
from eval_grid import analyse  # noqa: E402

REBUY = {"61", "62", "63", "64", "65", "68"}
GRIND = {"120"}


def is_rebuy(tag):
    t = (tag or "").split()
    return bool(t) and (all(c in REBUY for c in t) or (any(c in REBUY for c in t) and all(c in REBUY | GRIND for c in t)))


def trades(run):
    p = [f for f in glob.glob(f"D:/NostalgiaForInfinity/user_data/backtest_results/{run}/backtest-result-*.json")
         if "_config" not in f and "meta" not in f][0]
    return next(iter(json.load(open(p, encoding="utf-8"))["strategy"].values()))["trades"]


RUNS = {
    "W1": {"R0": "stopgrid-n25chk-X7SafeStopHonored", "RH": "stopgrid-r22-X7SafeRebuyHalf", "R25": "stopgrid-r22-X7SafeBothStop25"},
    "W4": {"R0": "stopgrid-r22w4-X7SafeStopHonored", "RH": "stopgrid-r22w4-X7SafeRebuyHalf", "R25": "stopgrid-r22w4-X7SafeBothStop25"},
    "W3": {"R0": "stopgrid-r22p-X7SafeStopHonored", "RH": "stopgrid-r22p-X7SafeRebuyHalf", "R25": "stopgrid-r22p-X7SafeBothStop25"},
}
M = {}
print(f"{'win':4s}{'arm':5s}{'ret':>9s}{'dd':>8s}{'ratio':>7s}{'sharpe':>8s}{'n':>5s}{'worst USDT':>11s}  rebuy n/net   other n/net   rebuy stops n/net")
for w, arms in RUNS.items():
    for a, run in arms.items():
        m = analyse(run)
        tr = trades(run)
        reb = [t for t in tr if is_rebuy(t["enter_tag"])]
        oth = [t for t in tr if not is_rebuy(t["enter_tag"])]
        rst = [t for t in reb if t["exit_reason"] in ("stop_loss", "trailing_stop_loss")]
        worst = min(t["profit_abs"] for t in tr)
        M[(w, a)] = dict(m, worst=worst)
        print(f"{w:4s}{a:5s}{m['ret']:8.2f}%{m['dd']:7.2f}%{m['ratio']:7.1f}{m['sharpe']:8.2f}{m['trades']:5d}{worst:11.0f}"
              f"  {len(reb):3d}/{sum(t['profit_abs'] for t in reb):7.0f}  {len(oth):3d}/{sum(t['profit_abs'] for t in oth):7.0f}"
              f"  {len(rst):3d}/{sum(t['profit_abs'] for t in rst):7.0f}")

for a in ("RH", "R25"):
    b1, v1 = M[("W1", "R0")], M[("W1", a)]
    b4, v4 = M[("W4", "R0")], M[("W4", a)]
    b3, v3 = M[("W3", "R0")], M[("W3", a)]
    checks = [
        (f"1) W1 ratio {v1['ratio']:.2f} >= 1.1 x {b1['ratio']:.2f} = {1.1 * b1['ratio']:.2f}", v1["ratio"] >= 1.1 * b1["ratio"]),
        (f"2) W1 dd {v1['dd']:.2f}% <= {b1['dd']:.2f}%", v1["dd"] <= b1["dd"] + 1e-9),
        (f"3) W1 sharpe {v1['sharpe']:.2f} >= {b1['sharpe']:.2f}", v1["sharpe"] >= b1["sharpe"]),
        (f"4) W4 ratio {v4['ratio']:.2f} >= {b4['ratio']:.2f} and dd {v4['dd']:.2f}% <= {b4['dd']:.2f}%",
         v4["ratio"] >= b4["ratio"] and v4["dd"] <= b4["dd"] + 1e-9),
        (f"5) W3 ret {v3['ret']:.2f}% >= {b3['ret']:.2f}% - 0.5", v3["ret"] >= b3["ret"] - 0.5),
        (f"6) W1 worst {v1['worst']:.0f} >= 1.5 x {b1['worst']:.0f} = {1.5 * b1['worst']:.0f}", v1["worst"] >= 1.5 * b1["worst"]),
    ]
    print(f"\n== {a}")
    for text, ok in checks:
        print(f"   {'PASS' if ok else 'FAIL'}  {text}")
    print(f"   VERDICT: {'CANDIDATE' if all(ok for _, ok in checks) else 'NOT ADOPTED'}")
