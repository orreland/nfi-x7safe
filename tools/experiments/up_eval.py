"""Upstream evaluation (reports/UPSTREAM_EVAL_2026-10-26.md 1.4/1.5): CUR vs UP."""
import glob
import json
import sys

sys.path.insert(0, r"D:\NostalgiaForInfinity\scripts")
from eval_grid import _result_json, analyse  # noqa: E402

PAIRS = {
    "W1": ("stopgrid-n25chk-X7SafeStopHonored", "up-w1-X7SafeStopHonored"),
    "W4": ("stopgrid-r22w4-X7SafeStopHonored", "up-w4-X7SafeStopHonored"),
    "W3": ("stopgrid-r22p-X7SafeStopHonored", "up-w3-X7SafeStopHonored"),
    "W2": ("stopgrid-curw2-X7SafeStopHonored", "up-w2-X7SafeStopHonored"),
}


def stats(run):
    p = _result_json(run)
    return next(iter(json.load(open(p, encoding="utf-8"))["strategy"].values())) if p else None


def pf(tr):
    w = sum(t["profit_abs"] for t in tr if t["profit_abs"] > 0)
    l = -sum(t["profit_abs"] for t in tr if t["profit_abs"] < 0)
    return w / l if l else float("inf")


M = {}
print(f"{'win':4s}{'arm':5s}{'ret':>9s}{'dd':>8s}{'ratio':>7s}{'sharpe':>8s}{'PF':>6s}{'n':>5s}{'win%':>7s}{'worst':>8s}")
for w, (cur, up) in PAIRS.items():
    for arm, run in (("CUR", cur), ("UP", up)):
        s = stats(run)
        if s is None:
            print(f"{w:4s}{arm:5s}  (missing: {run})")
            continue
        m = analyse(run)
        tr = s["trades"]
        M[(w, arm)] = dict(m, pf=pf(tr), n=len(tr))
        print(f"{w:4s}{arm:5s}{m['ret']:8.2f}%{m['dd']:7.2f}%{m['ratio']:7.1f}{m['sharpe']:8.2f}{pf(tr):6.2f}{len(tr):5d}"
              f"{100 * sum(t['profit_abs'] > 0 for t in tr) / len(tr):6.1f}%{min(t['profit_abs'] for t in tr):8.0f}")


def get(w, a):
    return M.get((w, a))


print()
checks = []
for w in ("W1", "W4", "W2"):
    c, u = get(w, "CUR"), get(w, "UP")
    if c and u:
        ok = u["ratio"] >= 0.95 * c["ratio"] and u["dd"] <= c["dd"] + 0.5
        checks.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {w}: ratio {u['ratio']:.2f} >= 0.95 x {c['ratio']:.2f} = {0.95 * c['ratio']:.2f}"
              f" and dd {u['dd']:.2f}% <= {c['dd']:.2f}% + 0.5")
    else:
        checks.append(False)
        print(f"MISSING {w}")
c3, u3 = get("W3", "CUR"), get("W3", "UP")
if c3 and u3:
    ok = u3["ret"] >= c3["ret"] - 0.5
    checks.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  W3: ret {u3['ret']:.2f}% >= {c3['ret']:.2f}% - 0.5")
c1, u1, c4, u4 = get("W1", "CUR"), get("W1", "UP"), get("W4", "CUR"), get("W4", "UP")
better = bool(c1 and u1 and c4 and u4 and u1["ratio"] >= 1.1 * c1["ratio"] and u4["ratio"] >= c4["ratio"])
print(f"\nB (not worse): {'PASS' if all(checks) else 'FAIL'}   C (clearly better): {'PASS' if better else 'FAIL'}")
