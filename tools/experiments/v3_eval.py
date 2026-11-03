"""Combined_V3 experiment evaluation (reports/V3_EXIT_EXPERIMENT_2026-10-25.md 1.5)."""
import glob
import json
import sys

sys.path.insert(0, r"D:\NostalgiaForInfinity\scripts")
from eval_grid import analyse  # noqa: E402

ARMS = ["Combined_V3", "Combined_V3_P05", "Combined_V3_P10", "Combined_V3_C2"]
SEGS = ["20250216-20250418", "20250418-20250618", "20250618-20250817", "20250817-20251017", "20251017-20251217",
        "20251217-20260216", "20260216-20260418", "20260418-20260617", "20260617-20260817", "20260817-20261017"]


def stats(run):
    p = [f for f in glob.glob(f"D:/NostalgiaForInfinity/user_data/backtest_results/{run}/backtest-result-*.json")
         if "_config" not in f and "meta" not in f][0]
    return next(iter(json.load(open(p, encoding="utf-8"))["strategy"].values()))


def pf(tr):
    w = sum(t["profit_abs"] for t in tr if t["profit_abs"] > 0)
    l = -sum(t["profit_abs"] for t in tr if t["profit_abs"] < 0)
    return w / l if l else float("inf")


V = {}
print(f"{'arm':18s}{'ret':>9s}{'dd':>8s}{'ratio':>7s}{'sharpe':>8s}{'PF':>6s}{'n':>5s}{'win%':>7s}{'avgW%':>7s}{'avgL%':>7s}  exits")
for a in ARMS:
    s = stats(f"v3-v1-{a}")
    m = analyse(f"v3-v1-{a}")
    tr = s["trades"]
    wins = [t for t in tr if t["profit_abs"] > 0]
    loss = [t for t in tr if t["profit_abs"] <= 0]
    ex = {}
    for t in tr:
        ex[t["exit_reason"]] = ex.get(t["exit_reason"], 0) + 1
    V[a] = dict(m, pf=pf(tr), n=len(tr))
    print(f"{a:18s}{m['ret']:8.2f}%{m['dd']:7.2f}%{m['ratio']:7.1f}{m['sharpe']:8.2f}{pf(tr):6.2f}{len(tr):5d}"
          f"{100 * len(wins) / len(tr):6.1f}%{100 * sum(t['profit_ratio'] for t in wins) / len(wins):7.2f}"
          f"{100 * sum(t['profit_ratio'] for t in loss) / max(len(loss), 1):7.2f}  {ex}")

seg = {a: [stats(f"v3-seg{i:02d}-{a}")["profit_total"] * 100 for i in range(1, 11)] for a in ARMS}
print("\nsegment returns (%):")
print(f"{'segment':20s}" + "".join(f"{a.replace('Combined_V3', 'B0').replace('B0_', ''):>9s}" for a in ARMS))
for i, sg in enumerate(SEGS):
    print(f"{sg:20s}" + "".join(f"{seg[a][i]:9.2f}" for a in ARMS))
print(f"{'sum':20s}" + "".join(f"{sum(seg[a]):9.2f}" for a in ARMS))

b = V["Combined_V3"]
verdict = {}
for a in ARMS[1:]:
    v = V[a]
    diff = [seg[a][i] - seg["Combined_V3"][i] for i in range(10)]
    best = max(range(10), key=lambda i: diff[i])
    rest_v = sum(seg[a][i] for i in range(10) if i != best)
    rest_b = sum(seg["Combined_V3"][i] for i in range(10) if i != best)
    checks = [
        (f"1) ratio {v['ratio']:.2f} >= 1.1 x {b['ratio']:.2f} = {1.1 * b['ratio']:.2f}", v["ratio"] >= 1.1 * b["ratio"]),
        (f"2) dd {v['dd']:.2f}% <= {b['dd']:.2f}%", v["dd"] <= b["dd"] + 1e-9),
        (f"3) PF {v['pf']:.2f} >= {b['pf']:.2f}", v["pf"] >= b["pf"]),
        (f"4) trades {v['n']} >= 0.7 x {b['n']} = {0.7 * b['n']:.0f}", v["n"] >= 0.7 * b["n"]),
        (f"5a) segments not worse (>= -0.5pp): {sum(d >= -0.5 for d in diff)}/10", sum(d >= -0.5 for d in diff) >= 7),
        (f"5b) without best segment ({SEGS[best]}, {diff[best]:+.2f}pp): {rest_v:.2f}% vs {rest_b:.2f}%", rest_v >= rest_b),
    ]
    verdict[a] = all(ok for _, ok in checks)
    print(f"\n== {a}: per-segment diff (pp) " + " ".join(f"{d:+.2f}" for d in diff))
    for t, ok in checks:
        print(f"   {'PASS' if ok else 'FAIL'}  {t}")
    print(f"   criteria 1-5: {'PASS' if verdict[a] else 'FAIL'}")
p05, p10 = verdict["Combined_V3_P05"], verdict["Combined_V3_P10"]
print(f"\n6) robustness P group: P05={'pass' if p05 else 'fail'} P10={'pass' if p10 else 'fail'}")
