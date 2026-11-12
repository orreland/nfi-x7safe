"""Combined_V3 round 3 evaluation (reports/V3_STOP_BANDX_2026-11-10.md 1.3, 1.4)."""
import glob
import json
import sys
from statistics import mean

sys.path.insert(0, r"D:\NostalgiaForInfinity\scripts")
from eval_grid import analyse  # noqa: E402

SEGS = ["20250216-20250418", "20250418-20250618", "20250618-20250817", "20250817-20251017", "20251017-20251217",
        "20251217-20260216", "20260216-20260418", "20260418-20260617", "20260617-20260817", "20260817-20261017"]
ARMS = ["B0", "B0T", "S3", "S4", "S7", "S10", "S15", "CS", "X", "XN"]
GRID = ["S3", "S4", "B0", "S7", "S10", "S15"]  # -3 -4 -5 -7 -10 -15


def cls(a):
  return "Combined_V3" if a == "B0" else f"Combined_V3_{a}"


def run(a, w):
  return f"v3-{w}-{cls(a)}"


def stats(r):
  p = [f for f in glob.glob(f"D:/NostalgiaForInfinity/user_data/backtest_results/{r}/backtest-result-*.json")
       if "_config" not in f and "meta" not in f][0]
  return next(iter(json.load(open(p, encoding="utf-8"))["strategy"].values()))


def pf(tr):
  w = sum(t["profit_abs"] for t in tr if t["profit_abs"] > 0)
  l = -sum(t["profit_abs"] for t in tr if t["profit_abs"] < 0)
  return w / l if l else float("inf")


V, SEG, TR, EXTRA = {}, {}, {}, {}
print(f"{'arm':5s}{'ret':>9s}{'dd':>8s}{'ratio':>7s}{'PF':>6s}{'n':>6s}{'win%':>7s}{'avgW%':>7s}{'avgL%':>7s}{'stops':>6s}{'avgStop%':>9s}  VP ret/n   VN ret/n   exits")
for a in ARMS:
  s, m = stats(run(a, "v1")), analyse(run(a, "v1"))
  tr = s["trades"]
  TR[a] = tr
  wins = [t for t in tr if t["profit_abs"] > 0]
  loss = [t for t in tr if t["profit_abs"] <= 0]
  stops = [t for t in tr if "stop" in t["exit_reason"]]
  ex = {}
  for t in tr:
    ex[t["exit_reason"]] = ex.get(t["exit_reason"], 0) + 1
  V[a] = dict(m, pf=pf(tr), n=len(tr))
  vp, vn = stats(run(a, "vp")), stats(run(a, "vn"))
  EXTRA[a] = (vp["profit_total"] * 100, len(vp["trades"]), vn["profit_total"] * 100, len(vn["trades"]))
  SEG[a] = [stats(run(a, f"seg{i:02d}"))["profit_total"] * 100 for i in range(1, 11)]
  print(f"{a:5s}{m['ret']:8.2f}%{m['dd']:7.2f}%{m['ratio']:7.2f}{pf(tr):6.2f}{len(tr):6d}{100 * len(wins) / len(tr):6.1f}%"
        f"{100 * mean([t['profit_ratio'] for t in wins] or [0]):7.2f}{100 * mean([t['profit_ratio'] for t in loss] or [0]):7.2f}"
        f"{len(stops):6d}{100 * mean([t['profit_ratio'] for t in stops] or [0]):9.2f}  {EXTRA[a][0]:6.2f}%/{EXTRA[a][1]:<4d} {EXTRA[a][2]:6.2f}%/{EXTRA[a][3]:<4d} {ex}")

same = [(t["pair"], t["open_date"], round(t["profit_abs"], 6)) for t in TR["B0"]] == [(t["pair"], t["open_date"], round(t["profit_abs"], 6)) for t in TR["B0T"]]
print(f"\nB0T reproduces B0 trade by trade: {same}; segments equal: {SEG['B0'] == SEG['B0T']}")

print("\nsegment returns (%):")
print(f"{'segment':20s}" + "".join(f"{a:>8s}" for a in ARMS))
for i, sg in enumerate(SEGS):
  print(f"{sg:20s}" + "".join(f"{SEG[a][i]:8.2f}" for a in ARMS))
print(f"{'sum':20s}" + "".join(f"{sum(SEG[a]):8.2f}" for a in ARMS))

b = V["B0"]
passed = {}
for a in ARMS[2:]:
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
  passed[a] = all(ok for _, ok in checks)
  print(f"\n== {a}: {'PASS 1-5' if passed[a] else 'FAIL'}   diff (pp) " + " ".join(f"{d:+.2f}" for d in diff))
  for t, ok in checks:
    print(f"   {'PASS' if ok else 'FAIL'}  {t}")

print("\n6) robustness")
for a in [g for g in GRID if g != "B0" and passed.get(g)]:
  i = GRID.index(a)
  nb = [GRID[j] for j in (i - 1, i + 1) if 0 <= j < len(GRID)]
  ok = all(V[n]["ratio"] >= b["ratio"] for n in nb)
  print(f"   {a}: neighbours {nb} ratios {[round(V[n]['ratio'], 2) for n in nb]} vs B0 {b['ratio']:.2f} -> {'robust' if ok else 'NOT robust (luck)'}")
if passed["X"] != passed["XN"]:
  other = "XN" if passed["X"] else "X"
  print(f"   X/XN: only one passes; the other ratio {V[other]['ratio']:.2f} vs B0 {b['ratio']:.2f} -> {'NOT robust' if V[other]['ratio'] < b['ratio'] else 'ok'}")
print("   candidates:", [a for a in ARMS[2:] if passed[a]] or "none passed 1-5")

print("\nrule A trades: B0T tag A vs X/XN tag X (V1)")
for a, tag in (("B0T", "A"), ("B0T", "B"), ("X", "X"), ("X", "B"), ("XN", "X"), ("XN", "B")):
  g = [t for t in TR[a] if (t.get("enter_tag") or "") == tag]
  if g:
    print(f"   {a:4s} rule {tag}: n {len(g):5d}  pnl {sum(t['profit_abs'] for t in g):+9.2f} USDT  win {100 * mean(t['profit_abs'] > 0 for t in g):5.1f}%"
          f"  avg {100 * mean(t['profit_ratio'] for t in g):+.2f}%  avg hold {mean(t['trade_duration'] for t in g) / 60:.1f} h")
