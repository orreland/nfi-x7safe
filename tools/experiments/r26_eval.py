"""Section-26 evaluation: rebuy hard-stop position grid on the N25 + E10 base."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from r22_eval import M as M22, is_rebuy, trades  # noqa: E402  (prints the section-23 table first)

sys.path.insert(0, r"D:\NostalgiaForInfinity\scripts")
from eval_grid import analyse  # noqa: E402

GRID = [("R10", 10), ("R12", 12), ("R0", 15), ("R18", 18), ("R20", 20), ("R25", 25), ("R30", 30), ("R40", 40)]
OLD = {"W1": {"R0": "stopgrid-n25chk-X7SafeStopHonored", "R25": "stopgrid-r22-X7SafeBothStop25"},
       "W4": {"R0": "stopgrid-r22w4-X7SafeStopHonored", "R25": "stopgrid-r22w4-X7SafeBothStop25"},
       "W3": {"R0": "stopgrid-r22p-X7SafeStopHonored", "R25": "stopgrid-r22p-X7SafeBothStop25"}}
TAG = {"W1": "r26", "W4": "r26w4", "W3": "r26p"}


def run_of(w, a, pct):
    return OLD[w].get(a) or f"stopgrid-{TAG[w]}-X7SafeRebuyStop{pct}"


M = {}
print("\n\n===== section 26 grid =====")
print(f"{'win':4s}{'arm':5s}{'ret':>9s}{'dd':>8s}{'ratio':>7s}{'sharpe':>8s}{'n':>5s}{'worst':>7s}"
      f"  rebuy n/net   other n/net   rebuy stops n/net  rebuy worst  rebuy adds")
for w in ("W1", "W4", "W3"):
    for a, pct in GRID:
        run = run_of(w, a, pct)
        m = analyse(run)
        tr = trades(run)
        reb = [t for t in tr if is_rebuy(t["enter_tag"])]
        oth = [t for t in tr if not is_rebuy(t["enter_tag"])]
        rst = [t for t in reb if t["exit_reason"] in ("stop_loss", "trailing_stop_loss")]
        worst = min(t["profit_abs"] for t in tr)
        rworst = min((t["profit_abs"] for t in reb), default=0)
        adds = sum(len([o for o in t.get("orders", []) if o.get("ft_is_entry")]) - 1 for t in reb)
        M[(w, a)] = dict(m, worst=worst, rnet=sum(t["profit_abs"] for t in reb))
        print(f"{w:4s}{a:5s}{m['ret']:8.2f}%{m['dd']:7.2f}%{m['ratio']:7.1f}{m['sharpe']:8.2f}{m['trades']:5d}{worst:7.0f}"
              f"  {len(reb):3d}/{sum(t['profit_abs'] for t in reb):7.0f}  {len(oth):3d}/{sum(t['profit_abs'] for t in oth):7.0f}"
              f"  {len(rst):3d}/{sum(t['profit_abs'] for t in rst):7.0f}  {rworst:9.0f}  {adds:5d}")

names = [a for a, _ in GRID]
b1, b4, b3 = M[("W1", "R0")], M[("W4", "R0")], M[("W3", "R0")]
passed = []
for i, a in enumerate(names):
    if a in ("R0", "R25"):
        continue
    v1, v4, v3 = M[("W1", a)], M[("W4", a)], M[("W3", a)]
    nb = [names[j] for j in (i - 1, i + 1) if 0 <= j < len(names)]
    checks = [
        (f"1) W1 ratio {v1['ratio']:.2f} >= {1.1 * b1['ratio']:.2f}", v1["ratio"] >= 1.1 * b1["ratio"]),
        (f"2) W1 dd {v1['dd']:.2f}% <= {b1['dd']:.2f}%", v1["dd"] <= b1["dd"] + 1e-9),
        (f"3) W1 sharpe {v1['sharpe']:.2f} >= {b1['sharpe']:.2f}", v1["sharpe"] >= b1["sharpe"]),
        (f"4) W4 ratio {v4['ratio']:.2f} >= {b4['ratio']:.2f} and dd {v4['dd']:.2f}% <= {b4['dd']:.2f}%",
         v4["ratio"] >= b4["ratio"] and v4["dd"] <= b4["dd"] + 1e-9),
        (f"5) W3 ret {v3['ret']:.2f}% >= {b3['ret'] - 0.5:.2f}%", v3["ret"] >= b3["ret"] - 0.5),
        (f"6) W1 worst {v1['worst']:.0f} >= {1.5 * b1['worst']:.0f}", v1["worst"] >= 1.5 * b1["worst"]),
        (f"7) neighbour {nb} W1 ratio >= {b1['ratio']:.2f}: " + ", ".join(f"{n} {M[('W1', n)]['ratio']:.2f}" for n in nb),
         any(M[("W1", n)]["ratio"] >= b1["ratio"] for n in nb)),
    ]
    ok = all(c for _, c in checks)
    passed += [a] if ok else []
    print(f"\n== {a}")
    for t, c in checks:
        print(f"   {'PASS' if c else 'FAIL'}  {t}")
    print(f"   criteria 1-7: {'PASS' if ok else 'FAIL'}")
print("\n8) passed:", passed or "none -> keep -15%")
