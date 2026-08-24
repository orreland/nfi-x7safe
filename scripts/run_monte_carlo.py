#!/usr/bin/env python
"""run_monte_carlo.py - Monte Carlo robustness check on top of an existing
freqtrade backtest result.

Why: a single 18-month backtest gives you ONE realized sequence of trades.
Its final return and max drawdown are one sample from a much wider range of
outcomes the same *edge* (win rate + average win/loss) could have produced
under a different trade order or under mild resampling noise - a strategy
that only "works" for the exact historical sequence it was tested on is a
red flag for luck/overfitting, not skill. This script:

  1. Loads the trade list from a backtest result JSON (run_backtest.py's
     output, or any --export=trades freqtrade result).
  2. Runs `--sims` Monte Carlo simulations two ways:
       a) bootstrap: resample trade returns WITH replacement (same trade
          count) - approximates "what if variance were slightly different".
       b) shuffle: reorder the SAME trades WITHOUT replacement - isolates
          pure sequence/path risk (e.g. "did all the winners cluster at the
          start by chance, hiding a later drawdown that could have come
          first").
  3. Reports the empirical distribution of final return and max drawdown
     across simulations (percentiles, probability of a loss, probability of
     a drawdown worse than common risk thresholds).

Usage:
  .venv\\Scripts\\python.exe scripts\\run_monte_carlo.py --result reports\\backtest_summary_20250216-20260816.json --sims 2000
  .venv\\Scripts\\python.exe scripts\\run_monte_carlo.py --result "user_data\\backtest_results\\backtest-result-single-....json" --sims 2000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nfi_backtest_lib import REPORTS  # noqa: E402


def load_trade_pnl(result_path: Path) -> tuple[list[float], float]:
    """Returns (profit_abs per trade, starting_balance). We deliberately use
    absolute $ P&L (additive against the starting balance) rather than
    compounding each trade's profit_ratio - NFI runs several concurrent
    positions sized off "unlimited" stake_amount, so no single trade ever
    risks 100% of equity the way naive cumprod(1+ratio) compounding assumes;
    that naive approach inflates results by orders of magnitude. Additive
    profit_abs / starting_balance is exactly how freqtrade itself computes
    profit_total, so this stays consistent with the real backtest numbers."""
    data = json.loads(result_path.read_text(encoding="utf-8"))
    if "metrics" in data and "result_json_path" in data.get("metrics", {}):
        # This is a run_backtest.py summary file - follow the pointer to the
        # raw freqtrade result which actually contains the trade list.
        raw_path = Path(data["metrics"]["result_json_path"])
        data = json.loads(raw_path.read_text(encoding="utf-8"))

    strategy_block = data.get("strategy", {})
    stats = next(iter(strategy_block.values())) if strategy_block else data
    trades = stats.get("trades")
    if not trades:
        raise SystemExit(
            "No 'trades' array found in the result JSON. Re-run the backtest with "
            "--export trades (run_backtest.py already does this) and point --result "
            "at that file."
        )
    pnl = [t["profit_abs"] for t in trades if t.get("profit_abs") is not None]
    if not pnl:
        raise SystemExit("Trades were found but none had a 'profit_abs' field.")
    starting_balance = stats.get("starting_balance") or stats.get("dry_run_wallet") or 10000.0
    return pnl, float(starting_balance)


def simulate_path(
    pnl: np.ndarray, starting_balance: float, rng: np.random.Generator, mode: str
) -> tuple[float, float]:
    """Returns (total_return_pct, max_drawdown_pct) for one simulated path,
    summing absolute trade P&L against a fixed starting balance (matches how
    freqtrade computes profit_total / max_drawdown_account for the real
    backtest - see load_trade_pnl)."""
    if mode == "bootstrap":
        path = rng.choice(pnl, size=len(pnl), replace=True)
    else:  # shuffle
        path = rng.permutation(pnl)

    equity = starting_balance + np.cumsum(path)
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    total_return_pct = (equity[-1] - starting_balance) / starting_balance * 100
    max_dd_pct = drawdown.min() * -100
    return total_return_pct, max_dd_pct


def summarize(samples: np.ndarray, label: str) -> dict:
    pct = lambda p: round(float(np.percentile(samples, p)), 3)  # noqa: E731
    return {
        "label": label,
        "mean": round(float(samples.mean()), 3),
        "p5": pct(5),
        "p25": pct(25),
        "median": pct(50),
        "p75": pct(75),
        "p95": pct(95),
        "worst": round(float(samples.min()), 3),
        "best": round(float(samples.max()), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", required=True, help="path to a backtest result JSON (raw or run_backtest.py summary)")
    parser.add_argument("--sims", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dd-thresholds", type=float, nargs="*", default=[15.0, 20.0, 30.0])
    args = parser.parse_args()

    pnl_list, starting_balance = load_trade_pnl(Path(args.result))
    pnl = np.array(pnl_list)
    print(f"[run_monte_carlo] loaded {len(pnl)} trades from {args.result}  (starting balance {starting_balance})")
    print(f"  observed mean trade P&L: {pnl.mean():.3f}   winrate: {(pnl > 0).mean() * 100:.2f}%")

    rng = np.random.default_rng(args.seed)
    results = {}
    for mode in ("bootstrap", "shuffle"):
        rets, dds = [], []
        for _ in range(args.sims):
            r, d = simulate_path(pnl, starting_balance, rng, mode)
            rets.append(r)
            dds.append(d)
        rets_arr, dds_arr = np.array(rets), np.array(dds)

        prob_loss = round(float((rets_arr < 0).mean() * 100), 2)
        dd_exceed = {
            f"p_drawdown_over_{int(t)}pct": round(float((dds_arr > t).mean() * 100), 2)
            for t in args.dd_thresholds
        }

        results[mode] = {
            "return_pct": summarize(rets_arr, f"{mode} total return %"),
            "max_drawdown_pct": summarize(dds_arr, f"{mode} max drawdown %"),
            "probability_of_loss_pct": prob_loss,
            **dd_exceed,
        }

        print(f"\n--- {mode} (n={args.sims}) ---")
        print(f"  return %      : median={results[mode]['return_pct']['median']}  "
              f"p5={results[mode]['return_pct']['p5']}  p95={results[mode]['return_pct']['p95']}")
        print(f"  max drawdown %: median={results[mode]['max_drawdown_pct']['median']}  "
              f"p5={results[mode]['max_drawdown_pct']['p5']}  p95={results[mode]['max_drawdown_pct']['p95']}")
        print(f"  P(final return < 0)  : {prob_loss}%")
        for k, v in dd_exceed.items():
            print(f"  P({k.replace('p_', '').replace('_', ' ')}) : {v}%")

    REPORTS.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS / f"monte_carlo_{Path(args.result).stem}.json"
    out_path.write_text(
        json.dumps(
            {"source": str(args.result), "n_trades": len(pnl), "sims": args.sims, "results": results},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nreport: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
