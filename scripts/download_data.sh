#!/usr/bin/env bash
# Download the candles the baselines need. No account or API key.
#   bash scripts/download_data.sh main   14 mainstream coins only, enough for main-* baselines
#   bash scripts/download_data.sh all    every universe, including delisted coins
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONUTF8=1
# pypatches stops ccxt asking for an API key on public data; without it: "binance requires apiKey credential".
if [ -x .venv/Scripts/python.exe ]; then
  PY=.venv/Scripts/python.exe
  PYTHONPATH="$(cygpath -w "$PWD/pypatches")"
else
  PY=.venv/bin/python
  PYTHONPATH="$PWD/pypatches"
fi
export PYTHONPATH
BASE=(--user-data-dir=./user_data --config=configs/exampleconfig.json --config=configs/exampleconfig_secret.json
      --config=configs/trading_mode-spot.json --config=configs/local-overrides-safe.json)
get() {
  "$PY" scripts/ft_delisted.py download-data "${BASE[@]}" "$@" --timeframes 5m 15m 1h 4h 1d --timerange 20250101-20261104
}
case "${1:-}" in
  main)
    get --config=configs/blacklist-binance.json --config=configs/pairlist-mainstream14.json
    ;;
  all)
    get --config=configs/blacklist-binance.json --config=configs/pairlist-backtest-static-binance-spot-usdt.json
    get --config=configs/blacklist-survivorship-test.json --config=configs/pairlist-survivorship-B-real-universe.json
    "$PY" scripts/fetch_delisted_data.py --start 2025-01 --end 2026-11
    ;;
  *)
    echo "usage: download_data.sh main|all" >&2
    exit 2
    ;;
esac
