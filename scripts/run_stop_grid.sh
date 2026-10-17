#!/usr/bin/env bash
# Runs the X7SafeStopVariants grid over the same window / universe / config
# chain as survB-safe-percent (the "stop denied" reference). Usage:
#   bash scripts/run_stop_grid.sh X7SafeStopHonored X7SafeStop12 ...
#
# Optional overrides (defaults reproduce the 2026-10-13 grid exactly):
#   TIMERANGE=20260830-20261017   backtest window
#   UNIVERSE=live                 server's dry-run universe (static pairlist +
#                                 real blacklist) instead of survB
#   TAG=parity                    result dir / log name: stopgrid-$TAG-$S
#   e.g. TIMERANGE=20260830-20261017 UNIVERSE=live TAG=parity bash scripts/run_stop_grid.sh X7SafeStopHonored
cd "$(dirname "$0")/.." || exit 1
# configs/*.json carry Chinese comments; without this Windows reads them as GBK.
export PYTHONUTF8=1
# Same ccxt apiKey shim nfi_backtest_lib.py loads (see pypatches/sitecustomize.py).
export PYTHONPATH="$(cygpath -w "$PWD/pypatches")"
TIMERANGE="${TIMERANGE:-20250216-20260816}"
case "${UNIVERSE:-survB}" in
  survB) UNIVERSE_CFG=(--config=configs/blacklist-survivorship-test.json
                       --config=configs/pairlist-survivorship-B-real-universe.json) ;;
  live)  UNIVERSE_CFG=(--config=configs/blacklist-binance.json
                       --config=configs/pairlist-backtest-static-binance-spot-usdt.json) ;;
  *) echo "unknown UNIVERSE=$UNIVERSE (survB|live)"; exit 1 ;;
esac
for S in "$@"; do
  NAME="${TAG:+$TAG-}$S"
  echo "=== START $NAME [$TIMERANGE ${UNIVERSE:-survB}] $(date +%T) ==="
  # Without an existing dir, freqtrade treats --backtest-directory as a file
  # prefix and drops stopgrid-$NAME-<ts>.zip next to it instead.
  mkdir -p "user_data/backtest_results/stopgrid-$NAME"
  .venv/Scripts/python.exe scripts/ft_delisted.py backtesting --strategy="$S" \
    --timerange="$TIMERANGE" --user-data-dir=./user_data \
    --config=configs/exampleconfig.json --config=configs/exampleconfig_secret.json \
    --config=configs/trading_mode-spot.json --config=configs/local-overrides-safe.json \
    "${UNIVERSE_CFG[@]}" \
    --enable-protections --breakdown month --export trades --cache none \
    --backtest-directory="user_data/backtest_results/stopgrid-$NAME" \
    > "logs_stopgrid_$NAME.log" 2>&1
  echo "=== DONE $NAME rc=$? $(date +%T) ==="
  grep -A3 "STRATEGY SUMMARY" "logs_stopgrid_$NAME.log" | tail -1
done
