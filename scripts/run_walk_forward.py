#!/usr/bin/env python
"""run_walk_forward.py - 10-window walk-forward validation (60-60-45 design)
for NostalgiaForInfinityX7 on Binance spot/USDT.

Window design (rolling, standard walk-forward layout):

    window i:  [------ train 60d ------][------ validate 60d ------][-- OOS 45d --]
    window i+1 starts `oos_days` (45d) later than window i, so the 10 OOS
    slices are back-to-back and non-overlapping, covering ~450 days; with the
    train+validate lead-in before the very first window, the full span is
    ~570 days (~18.7 months) - the closest even multiple of the design that
    still lines up with the requested trailing-18-month range.

IMPORTANT - what this script does NOT do: NostalgiaForInfinity ships as a
fixed, hand-tuned rule set, not a small parameter space meant to be
re-hyperopted from scratch on every fold within a single session (a proper
walk-forward *optimization* with hyperopt per window can easily take many
CPU-hours per fold). So "train" and "validate" here are NOT used to refit
parameters - they are run and reported purely as in-sample/near-sample
reference points, so you can see whether a window's out-of-sample (OOS)
result degrades sharply relative to what came right before it (a classic
overfitting/regime-shift red flag). The actual pass/fail verdict for each
window is based only on its OOS slice - the genuinely unseen-at-decision-time
data - which is what a walk-forward validation is meant to certify.

Each window checks four failure criteria on its OOS slice (see
nfi_backtest_lib.check_failure_criteria for the full rationale):
  1. winrate >= 85%          (NFI's own official CI bar; 0 trades = pass)
  2. max drawdown <= 15%     (NFI's own official CI bar)
  3. net OOS return >= 0%
  4. Sharpe ratio >= 0 (if available)

Outputs reports/walk_forward_report_<end>.json with per-window metrics, the
four-criteria pass/fail matrix, and an aggregate verdict.

Usage:
  .venv\\Scripts\\python.exe scripts\\run_walk_forward.py
  .venv\\Scripts\\python.exe scripts\\run_walk_forward.py --windows 10 --train-days 60 --validate-days 60 --oos-days 45
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


def build_windows(end: date, windows: int, train_days: int, validate_days: int, oos_days: int) -> list[dict]:
    """Windows are generated backwards from `end` so the last OOS slice ends
    exactly on `end`, then reversed into chronological order."""
    step = oos_days
    result = []
    for i in range(windows):
        oos_end = end - timedelta(days=step * i)
        oos_start = oos_end - timedelta(days=oos_days)
        validate_end = oos_start
        validate_start = validate_end - timedelta(days=validate_days)
        train_end = validate_start
        train_start = train_end - timedelta(days=train_days)
        result.append(
            {
                "index": None,  # filled after reversing
                "train_start": train_start,
                "train_end": train_end,
                "validate_start": validate_start,
                "validate_end": validate_end,
                "oos_start": oos_start,
                "oos_end": oos_end,
            }
        )
    result.reverse()
    for idx, w in enumerate(result, start=1):
        w["index"] = idx
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end", help="YYYYMMDD, default = today")
    parser.add_argument("--windows", type=int, default=10)
    parser.add_argument("--train-days", type=int, default=60)
    parser.add_argument("--validate-days", type=int, default=60)
    parser.add_argument("--oos-days", type=int, default=45)
    parser.add_argument("--strategy", default=STRATEGY)
    parser.add_argument(
        "--skip-in-sample",
        action="store_true",
        help="skip the train+validate reference backtest and only run the OOS slice (faster)",
    )
    parser.add_argument(
        "--extra-config", action="append", default=[], metavar="PATH",
        help="additional --config file(s) layered on top of the default chain; repeatable",
    )
    parser.add_argument(
        "--enable-protections", dest="enable_protections", action="store_true", default=None,
        help="honor the strategy's `protections` list during backtesting; "
             "auto-enabled for NostalgiaForInfinityX7Safe unless --no-protections is also given",
    )
    parser.add_argument(
        "--no-protections", dest="enable_protections", action="store_false",
        help="force protections off even for strategies that default them on",
    )
    parser.add_argument(
        "--label", default=None,
        help="suffix for the output report filename (default: derived from --strategy when non-default)",
    )
    args = parser.parse_args()
    label = args.label or (f"-{args.strategy}" if args.strategy != STRATEGY else "")
    extra_configs = [Path(p) for p in args.extra_config]

    end = date.fromisoformat(f"{args.end[:4]}-{args.end[4:6]}-{args.end[6:]}") if args.end else date.today()
    windows = build_windows(end, args.windows, args.train_days, args.validate_days, args.oos_days)

    total_span_days = (windows[-1]["oos_end"] - windows[0]["train_start"]).days
    print(
        f"[run_walk_forward] {args.windows} windows, "
        f"{args.train_days}-{args.validate_days}-{args.oos_days} design, "
        f"span {windows[0]['train_start']} -> {windows[-1]['oos_end']} "
        f"({total_span_days} days ~= {total_span_days / 30.44:.1f} months)"
    )

    per_window_results = []
    for w in windows:
        idx = w["index"]
        oos_s, oos_e = daterange_str(w["oos_start"]), daterange_str(w["oos_end"])
        is_s, is_e = daterange_str(w["train_start"]), daterange_str(w["validate_end"])
        print(f"\n--- window {idx}/{len(windows)} --- "
              f"train {w['train_start']}..{w['train_end']}  "
              f"validate {w['validate_start']}..{w['validate_end']}  "
              f"OOS {w['oos_start']}..{w['oos_end']}")

        entry = {
            "index": idx,
            "train_start": is_s,
            "validate_end": is_e,
            "oos_start": oos_s,
            "oos_end": oos_e,
        }

        try:
            oos_metrics = run_backtest(
                oos_s, oos_e, tag=f"wf{idx:02d}{label}-oos-{oos_s}-{oos_e}", strategy=args.strategy,
                extra_configs=extra_configs, enable_protections=args.enable_protections,
            )
            entry["oos"] = oos_metrics.to_dict()
            entry["oos_criteria"] = check_failure_criteria(oos_metrics)
        except BacktestError as exc:
            print(f"  [OOS] FAILED: {exc}", file=sys.stderr)
            entry["oos_error"] = str(exc)
            entry["oos_criteria"] = {"passed_all": False, "num_failed": 4, "error": True}

        if not args.skip_in_sample:
            try:
                is_metrics = run_backtest(
                    is_s, is_e, tag=f"wf{idx:02d}{label}-insample-{is_s}-{is_e}", strategy=args.strategy,
                    extra_configs=extra_configs, enable_protections=args.enable_protections,
                )
                entry["in_sample_reference"] = is_metrics.to_dict()
            except BacktestError as exc:
                print(f"  [in-sample reference] FAILED: {exc}", file=sys.stderr)
                entry["in_sample_error"] = str(exc)

        per_window_results.append(entry)

        if "oos" in entry:
            m = entry["oos"]
            c = entry["oos_criteria"]
            verdict = "PASS" if c["passed_all"] else f"FAIL ({c['num_failed']} criteria)"
            print(
                f"  OOS: trades={m['trades']} winrate={m['winrate_pct']}% "
                f"return={m['profit_total_pct']}% max_dd={m['max_drawdown_pct']}% "
                f"sharpe={m['sharpe']}  -> {verdict}"
            )

    windows_passed = sum(1 for r in per_window_results if r.get("oos_criteria", {}).get("passed_all"))
    windows_total = len(per_window_results)
    oos_returns = [r["oos"]["profit_total_pct"] for r in per_window_results if "oos" in r]
    profitable_windows = sum(1 for r in oos_returns if r > 0)

    aggregate = {
        "windows_total": windows_total,
        "windows_passed_all_criteria": windows_passed,
        "pass_rate_pct": round(100 * windows_passed / windows_total, 1) if windows_total else 0,
        "profitable_oos_windows": profitable_windows,
        "profitable_rate_pct": round(100 * profitable_windows / len(oos_returns), 1) if oos_returns else 0,
        "mean_oos_return_pct": round(sum(oos_returns) / len(oos_returns), 3) if oos_returns else None,
        "worst_oos_return_pct": round(min(oos_returns), 3) if oos_returns else None,
        "best_oos_return_pct": round(max(oos_returns), 3) if oos_returns else None,
    }
    # Simple, documented aggregate verdict: robust only if the large majority
    # of OOS windows individually clear all four criteria. This threshold is
    # our own choice (not an official NFI number) - see the final report.
    aggregate["verdict"] = (
        "ROBUST" if aggregate["pass_rate_pct"] >= 70 else
        "MARGINAL" if aggregate["pass_rate_pct"] >= 40 else
        "NOT ROBUST"
    )

    report = {
        "strategy": args.strategy,
        "design": {
            "windows": args.windows,
            "train_days": args.train_days,
            "validate_days": args.validate_days,
            "oos_days": args.oos_days,
            "step_days": args.oos_days,
            "span_start": daterange_str(windows[0]["train_start"]),
            "span_end": daterange_str(windows[-1]["oos_end"]),
        },
        "windows": per_window_results,
        "aggregate": aggregate,
    }

    REPORTS.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS / f"walk_forward_report{label}_{daterange_str(end)}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n===== WALK-FORWARD AGGREGATE =====")
    for k, v in aggregate.items():
        print(f"{k:28s}: {v}")
    print(f"\nfull report: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
