#!/usr/bin/env bash
# Run the T1 trend bot (user_data/strategies_trend/TrendDonchian.py) in dry-run: no API key, no real orders.
# Rules: reports/EXPERIMENTS_2026-11-03.md 1.4. Trades go to user_data/tradesv3.t1-dryrun.sqlite.
# usage: scripts/run_t1_dryrun.sh [extra freqtrade args]     stop with Ctrl+C
cd "$(dirname "$0")/.." || exit 1
export PYTHONUTF8=1
if [ -x .venv/Scripts/freqtrade.exe ]; then FT=.venv/Scripts/freqtrade.exe; else FT=.venv/bin/freqtrade; fi
mkdir -p user_data/logs
exec "$FT" trade --config configs/t1-dryrun.example.json --strategy-path user_data/strategies_trend \
  --user-data-dir ./user_data --logfile user_data/logs/t1-dryrun.log "$@"
