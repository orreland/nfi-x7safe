#!/usr/bin/env python
"""run_backtest.py - one-click 18-month continuous backtest for
NostalgiaForInfinityX7 on Binance spot/USDT.

What it does:
  1. Calls `freqtrade backtesting` with the exact config chain NFI's own CI
     uses (configs/exampleconfig*.json + trading_mode-spot.json +
     blacklist-binance.json + pairlist-backtest-static-binance-spot-usdt.json).
  2. Runs it over a single continuous time range (default: trailing 18
     months from today).
  3. Saves freqtrade's raw result JSON under user_data/backtest_results/.
  4. Prints and saves a compact summary of the key metrics (total return,
     max drawdown, Sharpe/Sortino/Calmar, win rate, profit factor, ...) to
     reports/backtest_summary_<start>-<end>.json.

Usage:
  .venv\\Scripts\\python.exe scripts\\run_backtest.py
  .venv\\Scripts\\python.exe scripts\\run_backtest.py --start 20250216 --end 20260816
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nfi_backtest_lib import (  # noqa: E402
    REPORTS,
    STRATEGY,
    BacktestError,
    check_failure_criteria,
    daterange_str,
    run_backtest,
)


def default_range(months: int = 18) -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=round(months * 30.44))
    return daterange_str(start), daterange_str(end)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", help="YYYYMMDD, default = 18 months before --end")
    parser.add_argument("--end", help="YYYYMMDD, default = today")
    parser.add_argument("--months", type=int, default=18, help="window length if --start omitted")
    parser.add_argument("--strategy", default=STRATEGY)
    parser.add_argument(
        "--extra-config", action="append", default=[], metavar="PATH",
        help="additional --config file(s) layered on top of the default chain; repeatable",
    )
    parser.add_argument(
        "--enable-protections", dest="enable_protections", action="store_true", default=None,
        help="honor the strategy's `protections` list during backtesting (freqtrade otherwise ignores it); "
             "auto-enabled for NostalgiaForInfinityX7Safe unless --no-protections is also given",
    )
    parser.add_argument(
        "--no-protections", dest="enable_protections", action="store_false",
        help="force protections off even for strategies that default them on",
    )
    parser.add_argument(
        "--label", default=None,
        help="suffix for the output report filename, so runs with different configs don't overwrite "
             "each other (default: derived from --strategy when it isn't the default strategy)",
    )
    args = parser.parse_args()

    default_start, default_end = default_range(args.months)
    start = args.start or default_start
    end = args.end or default_end
    label = args.label or (f"-{args.strategy}" if args.strategy != STRATEGY else "")

    print(f"[run_backtest] strategy={args.strategy} timerange={start}-{end} "
          f"extra_configs={args.extra_config} enable_protections={args.enable_protections}")
    try:
        metrics = run_backtest(
            start, end, tag=f"single{label}-{start}-{end}", strategy=args.strategy,
            extra_configs=[Path(p) for p in args.extra_config],
            enable_protections=args.enable_protections,
        )
    except BacktestError as exc:
        print(f"[run_backtest] FAILED: {exc}", file=sys.stderr)
        return 1

    criteria = check_failure_criteria(metrics)

    REPORTS.mkdir(parents=True, exist_ok=True)
    summary_path = REPORTS / f"backtest_summary{label}_{start}-{end}.json"
    summary_path.write_text(
        json.dumps({"metrics": metrics.to_dict(), "criteria": criteria}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n===== SUMMARY =====")
    print(f"period            : {start} - {end}")
    print(f"trades            : {metrics.trades}  (wins {metrics.wins} / losses {metrics.losses})")
    print(f"winrate           : {metrics.winrate_pct}%")
    print(f"total return      : {metrics.profit_total_pct}%")
    print(f"max drawdown      : {metrics.max_drawdown_pct}%")
    print(f"sharpe / sortino  : {metrics.sharpe} / {metrics.sortino}")
    print(f"calmar / cagr     : {metrics.calmar} / {metrics.cagr}")
    print(f"profit factor     : {metrics.profit_factor}")
    print(f"market change     : {metrics.market_change_pct}%  (buy & hold baseline)")
    print(f"failure criteria  : {criteria}")
    print(f"\nraw result json   : {metrics.result_json_path}")
    print(f"summary json      : {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
