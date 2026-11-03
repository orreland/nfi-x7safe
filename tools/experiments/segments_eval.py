"""Section-16 segment consistency check: per-segment return / drawdown for
baseline, N25, N0 and the four pre-registered criteria."""
import glob
import json

SEGS = ["20250216-20250418", "20250418-20250618", "20250618-20250817", "20250817-20251017", "20251017-20251217",
        "20251217-20260216", "20260216-20260418", "20260418-20260617", "20260617-20260817", "20260817-20261017"]
ARMS = {"base": "X7SafeStopHonored", "N25": "X7SafeOtherStop25", "N0": "X7SafeOtherNoStop"}


def stats(run):
    p = [f for f in glob.glob(f"D:/NostalgiaForInfinity/user_data/backtest_results/{run}/backtest-result-*.json")
         if "_config" not in f and "meta" not in f][0]
    s = next(iter(json.load(open(p, encoding="utf-8"))["strategy"].values()))
    return s["profit_total"] * 100, s.get("max_drawdown_account", 0.0) * 100, s["total_trades"]


res = {a: [] for a in ARMS}
for i, seg in enumerate(SEGS, 1):
    for a, cls in ARMS.items():
        res[a].append(stats(f"stopgrid-seg{i:02d}-{cls}"))

print(f"{'segment':20s}" + "".join(f"{a + ' ret':>10s}{a + ' dd':>9s}{a + ' n':>6s}" for a in ARMS))
for i, seg in enumerate(SEGS):
    print(f"{seg:20s}" + "".join(f"{res[a][i][0]:9.2f}%{res[a][i][1]:8.2f}%{res[a][i][2]:6d}" for a in ARMS))
print(f"{'sum of returns':20s}" + "".join(f"{sum(r[0] for r in res[a]):9.2f}%{'':14s}" for a in ARMS))

base = res["base"]
for a in ("N25", "N0"):
    v = res[a]
    diff = [v[i][0] - base[i][0] for i in range(len(SEGS))]
    c1 = sum(d >= -0.5 for d in diff)
    best = max(range(len(SEGS)), key=lambda i: diff[i])
    rest_v = sum(v[i][0] for i in range(len(SEGS)) if i != best)
    rest_b = sum(base[i][0] for i in range(len(SEGS)) if i != best)
    c3_v, c3_b = min(r[0] for r in v), min(r[0] for r in base)
    c4 = sum(v[i][1] <= base[i][1] + 0.5 for i in range(len(SEGS)))
    ok = [c1 >= 7, rest_v >= rest_b, c3_v >= c3_b - 1.0, c4 >= 7]
    print(f"\n== {a}: per-segment diff vs base (pp): " + " ".join(f"{d:+.2f}" for d in diff))
    print(f"   1) segments not worse (>= -0.5pp): {c1}/10 -> {'PASS' if ok[0] else 'FAIL'}")
    print(f"   2) without best segment ({SEGS[best]}, {diff[best]:+.2f}pp): {rest_v:.2f}% vs base {rest_b:.2f}% -> {'PASS' if ok[1] else 'FAIL'}")
    print(f"   3) worst segment {c3_v:.2f}% vs base {c3_b:.2f}% (-1pp allowed) -> {'PASS' if ok[2] else 'FAIL'}")
    print(f"   4) segments with dd <= base+0.5pp: {c4}/10 -> {'PASS' if ok[3] else 'FAIL'}")
    print(f"   VERDICT: {'PASS' if all(ok) else 'FAIL'}")
