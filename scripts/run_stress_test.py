#!/usr/bin/env python
"""run_stress_test.py - two more practical robustness checks that
run_backtest.py / run_walk_forward.py don't cover:

  1. Fee / slippage sensitivity: NFI trades frequently and uses DCA
     ("grinding") re-entries, so it does many small orders - a strategy
     whose edge quietly depends on near-zero execution cost is fragile in
     live trading (real fills slip, spreads widen in volatility, and
     Binance's real taker fee is rarely the best-case rate people assume).
     freqtrade's backtester does not simulate order-book slippage directly,
     so - as is standard practice in the freqtrade community - we use the
     configurable per-trade `fee` as a slippage *proxy* and re-run the same
     18-month backtest at multiple fee levels (0.10% baseline / 0.15% /
     0.20% / 0.30% round-trip-equivalent) to see how much of the edge
     survives realistic-to-pessimistic execution cost.

  2. Pair-concentration check: re-reads the trades from an existing backtest
     result and reports how much of total profit came from the top-N pairs.
     If a handful of pairs (or one huge outlier trade) account for most of
     the return, the strategy's live performance is much more exposed to
     "did that one coin pump again" luck than the aggregate win rate alone
     would suggest - a classic backtest overfitting/robustness red flag.

Usage:
  .venv\\Scripts\\python.exe scripts\\run_stress_test.py --start 20250216 --end 20260816
  .venv\\Scripts\\python.exe scripts\\run_stress_test.py --start 20250216 --end 20260816 --skip-fee-sweep --concentration-from reports\\backtest_summary_20250216-20260816.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nfi_backtest_lib import CONFIGS, REPORTS, STRATEGY, BacktestError, run_backtest  # noqa: E402

DEFAULT_FEE_LEVELS_PCT = [0.10, 0.15, 0.20, 0.30]


def write_fee_config(fee_pct: float, tmp_dir: Path) -> Path:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = tmp_dir / f"fee-{fee_pct}pct.json"
    cfg_path.write_text(json.dumps({"fee": round(fee_pct / 100, 5)}), encoding="utf-8")
    return cfg_path


def fee_sweep(start: str, end: str, strategy: str, fee_levels_pct: list[float]) -> list[dict]:
    tmp_dir = CONFIGS / "_stress_fee_overrides"
    rows = []
    for fee_pct in fee_levels_pct:
        cfg = write_fee_config(fee_pct, tmp_dir)
        tag = f"stress-fee-{fee_pct}pct-{start}-{end}"
        print(f"[fee_sweep] running backtest at fee={fee_pct}% round-trip...")
        try:
            m = run_backtest(start, end, tag=tag, strategy=strategy, extra_configs=[cfg])
            rows.append(
                {
                    "fee_pct": fee_pct,
                    "trades": m.trades,
                    "winrate_pct": m.winrate_pct,
                    "total_return_pct": m.profit_total_pct,
                    "max_drawdown_pct": m.max_drawdown_pct,
                    "sharpe": m.sharpe,
                }
            )
            print(f"  -> return={m.profit_total_pct}%  max_dd={m.max_drawdown_pct}%  sharpe={m.sharpe}")
        except BacktestError as exc:
            print(f"  FAILED at fee={fee_pct}%: {exc}", file=sys.stderr)
            rows.append({"fee_pct": fee_pct, "error": str(exc)})
    return rows


def _load_trades(result_path: Path) -> list[dict]:
    data = json.loads(result_path.read_text(encoding="utf-8"))
    if "metrics" in data and "result_json_path" in data.get("metrics", {}):
        data = json.loads(Path(data["metrics"]["result_json_path"]).read_text(encoding="utf-8"))
    strategy_block = data.get("strategy", {})
    stats = next(iter(strategy_block.values())) if strategy_block else data
    trades = stats.get("trades") or []
    if not trades:
        raise SystemExit(f"No trades found in {result_path}. Re-run with --export trades.")
    return trades


def pair_concentration(result_path: Path, top_n: int = 10) -> dict:
    trades = _load_trades(result_path)
    profit_by_pair: dict[str, float] = defaultdict(float)
    for t in trades:
        profit_by_pair[t.get("pair", "?")] += t.get("profit_abs", 0.0) or 0.0

    total_profit = sum(profit_by_pair.values())
    ranked = sorted(profit_by_pair.items(), key=lambda kv: kv[1], reverse=True)
    top = ranked[:top_n]
    top_sum = sum(v for _, v in top)
    top_share_pct = round(100 * top_sum / total_profit, 1) if total_profit else None

    return {
        "total_pairs_traded": len(profit_by_pair),
        "total_profit_abs": round(total_profit, 2),
        "top_pairs": [{"pair": p, "profit_abs": round(v, 2)} for p, v in top],
        "top_n": top_n,
        "top_n_share_of_total_profit_pct": top_share_pct,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--strategy", default=STRATEGY)
    parser.add_argument("--fee-levels-pct", type=float, nargs="*", default=DEFAULT_FEE_LEVELS_PCT)
    parser.add_argument("--skip-fee-sweep", action="store_true")
    parser.add_argument(
        "--concentration-from",
        help="existing backtest result JSON to analyze for pair concentration "
        "(default: run a fresh baseline backtest for --start/--end)",
    )
    parser.add_argument("--top-n", type=int, default=10)
    args = parser.parse_args()

    report: dict = {"start": args.start, "end": args.end, "strategy": args.strategy}

    if not args.skip_fee_sweep:
        report["fee_sweep_pct_round_trip"] = fee_sweep(args.start, args.end, args.strategy, args.fee_levels_pct)

    if args.concentration_from:
        conc_source = Path(args.concentration_from)
    else:
        print("[concentration] running baseline backtest for pair-concentration analysis...")
        m = run_backtest(args.start, args.end, tag=f"stress-baseline-{args.start}-{args.end}", strategy=args.strategy)
        conc_source = Path(m.result_json_path)

    report["pair_concentration"] = pair_concentration(conc_source, top_n=args.top_n)

    REPORTS.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS / f"stress_test_{args.start}-{args.end}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n===== STRESS TEST SUMMARY =====")
    if "fee_sweep_pct_round_trip" in report:
        for row in report["fee_sweep_pct_round_trip"]:
            if "error" in row:
                print(f"  fee={row['fee_pct']}%: ERROR")
            else:
                print(
                    f"  fee={row['fee_pct']}%: return={row['total_return_pct']}%  "
                    f"max_dd={row['max_drawdown_pct']}%  sharpe={row['sharpe']}"
                )
    c = report["pair_concentration"]
    print(f"\n  pairs traded: {c['total_pairs_traded']}")
    print(f"  top {c['top_n']} pairs = {c['top_n_share_of_total_profit_pct']}% of total profit")
    for p in c["top_pairs"][:5]:
        print(f"    {p['pair']:15s} {p['profit_abs']}")
    print(f"\nreport: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
