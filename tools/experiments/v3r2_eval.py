"""Combined_V3 round 2 evaluation (reports/V3_ROUND2_2026-10-26.md 1.4)."""
import glob
import json
import sys

sys.path.insert(0, r"D:\NostalgiaForInfinity\scripts")
from eval_grid import analyse  # noqa: E402

SEGS = ["20250216-20250418", "20250418-20250618", "20250618-20250817", "20250817-20251017", "20251017-20251217",
        "20251217-20260216", "20260216-20260418", "20260418-20260617", "20260617-20260817", "20260817-20261017"]
# arm -> (V1 run, VP run, segment run pattern)
ARMS = {
    "B0": ("v3-v1-Combined_V3", "v3-vp-Combined_V3", "v3-seg{:02d}-Combined_V3"),
    "K1": ("v3-v1-Combined_V3_K1", "v3-vp-Combined_V3_K1", "v3-seg{:02d}-Combined_V3_K1"),
    "K2": ("v3-v1-Combined_V3_K2", "v3-vp-Combined_V3_K2", "v3-seg{:02d}-Combined_V3_K2"),
    "T12": ("v3-v1-Combined_V3_T12", "v3-vp-Combined_V3_T12", "v3-seg{:02d}-Combined_V3_T12"),
    "T24": ("v3-v1-Combined_V3_T24", "v3-vp-Combined_V3_T24", "v3-seg{:02d}-Combined_V3_T24"),
    "U20": ("v3-v1u20-Combined_V3", "v3-vpu20-Combined_V3", "v3-seg{:02d}u20-Combined_V3"),
    "PC": ("v3-v1-Combined_V3_PC", "v3-vp-Combined_V3_PC", "v3-seg{:02d}-Combined_V3_PC"),
}


def stats(run):
    p = [f for f in glob.glob(f"D:/NostalgiaForInfinity/user_data/backtest_results/{run}/backtest-result-*.json")
         if "_config" not in f and "meta" not in f][0]
    return next(iter(json.load(open(p, encoding="utf-8"))["strategy"].values()))


def pf(tr):
    w = sum(t["profit_abs"] for t in tr if t["profit_abs"] > 0)
    l = -sum(t["profit_abs"] for t in tr if t["profit_abs"] < 0)
    return w / l if l else float("inf")


V, VP, SEG = {}, {}, {}
print(f"{'arm':5s}{'ret':>9s}{'dd':>8s}{'ratio':>7s}{'sharpe':>8s}{'PF':>6s}{'n':>5s}{'win%':>7s}{'avgW%':>7s}{'avgL%':>7s}  exits   | VP ret / n")
for a, (v1, vp, sp) in ARMS.items():
    s = stats(v1)
    m = analyse(v1)
    tr = s["trades"]
    wins = [t for t in tr if t["profit_abs"] > 0]
    loss = [t for t in tr if t["profit_abs"] <= 0]
    ex = {}
    for t in tr:
        k = t["exit_reason"] if not t["exit_reason"].startswith("time_stop") else "time_stop"
        ex[k] = ex.get(k, 0) + 1
    V[a] = dict(m, pf=pf(tr), n=len(tr))
    vps = stats(vp)
    VP[a] = (vps["profit_total"] * 100, len(vps["trades"]))
    SEG[a] = [stats(sp.format(i))["profit_total"] * 100 for i in range(1, 11)]
    print(f"{a:5s}{m['ret']:8.2f}%{m['dd']:7.2f}%{m['ratio']:7.2f}{m['sharpe']:8.2f}{pf(tr):6.2f}{len(tr):5d}"
          f"{100 * len(wins) / len(tr):6.1f}%{100 * sum(t['profit_ratio'] for t in wins) / max(len(wins), 1):7.2f}"
          f"{100 * sum(t['profit_ratio'] for t in loss) / max(len(loss), 1):7.2f}  {ex}  | {VP[a][0]:6.2f}% / {VP[a][1]}")

print("\nsegment returns (%):")
print(f"{'segment':20s}" + "".join(f"{a:>8s}" for a in ARMS))
for i, sg in enumerate(SEGS):
    print(f"{sg:20s}" + "".join(f"{SEG[a][i]:8.2f}" for a in ARMS))
print(f"{'sum':20s}" + "".join(f"{sum(SEG[a]):8.2f}" for a in ARMS))

b = V["B0"]
verdict = {}
for a in list(ARMS)[1:]:
    v = V[a]
    diff = [SEG[a][i] - SEG["B0"][i] for i in range(10)]
    best = max(range(10), key=lambda i: diff[i])
    rest_v = sum(SEG[a][i] for i in range(10) if i != best)
    rest_b = sum(SEG["B0"][i] for i in range(10) if i != best)
    checks = [
        (f"1) ratio {v['ratio']:.2f} >= {1.1 * b['ratio']:.2f}", v["ratio"] >= 1.1 * b["ratio"]),
        (f"2) dd {v['dd']:.2f}% <= {b['dd']:.2f}%", v["dd"] <= b["dd"] + 1e-9),
        (f"3) PF {v['pf']:.2f} >= {b['pf']:.2f}", v["pf"] >= b["pf"]),
        (f"4) trades {v['n']} >= {0.7 * b['n']:.0f}", v["n"] >= 0.7 * b["n"]),
        (f"5a) segments not worse: {sum(d >= -0.5 for d in diff)}/10", sum(d >= -0.5 for d in diff) >= 7),
        (f"5b) without best ({SEGS[best]} {diff[best]:+.2f}pp): {rest_v:.2f}% vs {rest_b:.2f}%", rest_v >= rest_b),
    ]
    verdict[a] = all(ok for _, ok in checks)
    print(f"\n== {a}: diff (pp) " + " ".join(f"{d:+.2f}" for d in diff))
    for t, ok in checks:
        print(f"   {'PASS' if ok else 'FAIL'}  {t}")
    print(f"   criteria 1-5: {'PASS' if verdict[a] else 'FAIL'}")
print("\n6) robustness: K1/K2", verdict["K1"], verdict["K2"], " T12/T24", verdict["T12"], verdict["T24"])
