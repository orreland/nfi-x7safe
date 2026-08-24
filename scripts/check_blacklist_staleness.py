#!/usr/bin/env python
"""check_blacklist_staleness.py - early-warning check for the "should have been
blacklisted already" problem, not the "already blacklisted" one.

WHY THIS EXISTS
---------------
Section 08 of the survivorship analysis (reports/SAFE_ONLY.md 第四节) found that
the 40 pairs configs/blacklist-binance.json excludes are, checked today, 100%
delisted from Binance spot. Every one of those blacklist entries was added
AFTER the coin died (the file's own comments carry dates like "Binance delist
2026-08-17", "Token collapse 2026-07-21"). A hard stop (what X7Safe adds)
limits the damage from a coin that's already crashing; it does nothing for a
coin that hasn't started crashing yet but is about to be delisted - the
strategy will happily keep entering it right up until the exchange pulls it.

This script does not try to predict delistings. It only surfaces two cheap,
mechanical signals that are available *before* an official announcement lands
in the community-maintained blacklist:

  1. A pair currently in the trading whitelist has a Binance symbol status that isn't `TRADING` on
     Binance's public exchangeInfo endpoint - i.e. trading has already been
     suspended, but the local blacklist file hasn't caught up yet. By the
     time this fires the coin may already be unenterable, but existing OPEN
     positions in it should be flagged for manual attention immediately
     rather than waiting for the next scheduled blacklist sync.
  2. A pair's recent daily trading volume has collapsed relative to its own
     trailing baseline - a common precursor to delisting (though also
     produced by ordinary low-volatility periods, hence "candidate" not
     "confirmed").

Neither signal is a verdict. Both are meant to shorten the gap between "the
market already knows something is wrong" and "a human looks at it", which is
the actual gap this project's blacklist depends on closing.

USAGE
  .venv\\Scripts\\python.exe scripts\\check_blacklist_staleness.py
  .venv\\Scripts\\python.exe scripts\\check_blacklist_staleness.py --volume-drop-pct 80

Read-only. No API key, no orders, no config changes. Safe to run anytime,
including against a live account (uses public market data only).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIGS = ROOT / "configs"
BINANCE_EXCHANGE_INFO_URL = "https://api.binance.com/api/v3/exchangeInfo"


def load_whitelist() -> list[str]:
    raw = (CONFIGS / "pairlist-backtest-static-binance-spot-usdt.json").read_text(encoding="utf-8")
    data = json.loads(re.sub(r"//.*", "", raw))
    return data["exchange"]["pair_whitelist"]


def check_inactive_markets(pairs: list[str]) -> list[dict]:
    """Signal 1: pairs whose Binance symbol status isn't TRADING.

    Hits Binance's public /api/v3/exchangeInfo REST endpoint directly rather
    than going through ccxt: this project's pinned ccxt version signs several
    load_markets() sub-requests unconditionally even with fetchMarkets
    restricted to spot, and fails with no API key configured (a different,
    deeper issue than the apiKey="" bug pypatches/sitecustomize.py works
    around). exchangeInfo is a public, unauthenticated, no-key-required
    endpoint and is all this check actually needs.
    """
    import json as _json
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(BINANCE_EXCHANGE_INFO_URL, timeout=20) as resp:
            data = _json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"[warn] could not reach Binance exchangeInfo ({exc}), skipping inactive-market check", file=sys.stderr)
        return []

    by_symbol = {s["symbol"]: s for s in data.get("symbols", [])}
    flagged = []
    for pair in pairs:
        symbol = pair.replace("/", "")
        info = by_symbol.get(symbol)
        if info is None:
            flagged.append({"pair": pair, "reason": "not_in_exchange_info", "detail": "gone from exchangeInfo entirely"})
        elif info.get("status") != "TRADING":
            flagged.append({"pair": pair, "reason": "inactive", "detail": f"status={info.get('status')}"})
    return flagged


def check_volume_collapse(pairs: list[str], drop_pct: float, lookback_days: int, recent_days: int) -> list[dict]:
    """Signal 2: recent daily volume far below the pair's own trailing baseline.

    Uses locally cached 1d OHLCV under user_data/data/binance/ if present
    (no network calls) - run `freqtrade download-data --timeframes 1d` first
    if a pair is missing.
    """
    try:
        import pandas as pd
    except ImportError:
        print("[warn] pandas not available, skipping volume-collapse check", file=sys.stderr)
        return []

    data_dir = ROOT / "user_data" / "data" / "binance"
    flagged = []
    for pair in pairs:
        path = data_dir / f"{pair.replace('/', '_')}-1d.feather"
        if not path.exists():
            continue
        try:
            df = pd.read_feather(path)
        except Exception:  # noqa: BLE001
            continue
        if len(df) < lookback_days + recent_days:
            continue
        df = df.sort_values("date")
        baseline = df["volume"].iloc[-(lookback_days + recent_days) : -recent_days].mean()
        recent = df["volume"].iloc[-recent_days:].mean()
        if baseline <= 0:
            continue
        drop = (1 - recent / baseline) * 100
        if drop >= drop_pct:
            flagged.append(
                {
                    "pair": pair,
                    "reason": "volume_collapse",
                    "detail": f"{recent_days}d avg volume down {drop:.0f}% vs preceding {lookback_days}d "
                    f"({recent:.0f} vs {baseline:.0f})",
                }
            )
    return flagged


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--volume-drop-pct", type=float, default=80.0, help="flag if recent volume is down this much (%%)")
    ap.add_argument("--lookback-days", type=int, default=60, help="baseline window for the volume check")
    ap.add_argument("--recent-days", type=int, default=7, help="recent window compared against the baseline")
    ap.add_argument("--skip-market-check", action="store_true", help="skip the live ccxt inactive-market check")
    ap.add_argument("--skip-volume-check", action="store_true", help="skip the local-data volume-collapse check")
    args = ap.parse_args()

    pairs = load_whitelist()
    print(f"checking {len(pairs)} whitelisted pairs for early delisting signals...\n")

    findings: list[dict] = []
    if not args.skip_market_check:
        findings += check_inactive_markets(pairs)
    if not args.skip_volume_check:
        findings += check_volume_collapse(pairs, args.volume_drop_pct, args.lookback_days, args.recent_days)

    if not findings:
        print("no candidates found. this does NOT mean the blacklist is up to date -")
        print("it means neither cheap signal tripped. still check exchange announcements manually.")
        return 0

    print(f"{len(findings)} candidate(s) - none of these are automatic blacklist decisions, review each:\n")
    for f in findings:
        print(f"  [{f['reason']:16s}] {f['pair']:14s} {f['detail']}")

    print(
        "\nnext step for anything flagged above: check Binance's announcement page and the "
        "NFI Discord monitoring channel before adding to configs/blacklist-binance.json - "
        "these signals are cheap and noisy by design, not a verdict."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
