#!/usr/bin/env bash
# Combined_V3 backtests (report reports/V3_EXIT_EXPERIMENT_2026-10-25.md).
# usage: TIMERANGE=... TAG=... bash scratch/tools/run_v3.sh Strategy [Strategy ...]
cd /d/NostalgiaForInfinity || exit 1
export PYTHONUTF8=1 PYTHONPATH="$(cygpath -w "$PWD/pypatches")" FT_LOWMEM=1
export TEMP='D:\NostalgiaForInfinity\scratch\tmp' TMP='D:\NostalgiaForInfinity\scratch\tmp'
TIMERANGE="${TIMERANGE:-20250216-20261017}"
for S in "$@"; do
  NAME="v3${TAG:+-$TAG}-$S"
  mkdir -p "user_data/backtest_results/$NAME"
  echo "=== START $NAME [$TIMERANGE] $(date +%T) ==="
  .venv/Scripts/freqtrade.exe backtesting --strategy="$S" --strategy-path=user_data/strategies_v3 \
    --timerange="$TIMERANGE" --user-data-dir=./user_data --config="${CONFIG:-configs/v3-backtest.json}" \
    --enable-protections --export trades --cache none \
    --backtest-directory="user_data/backtest_results/$NAME" > "scratch/tmp/log_$NAME.log" 2>&1
  echo "=== DONE $NAME rc=$? $(date +%T) ==="
done
