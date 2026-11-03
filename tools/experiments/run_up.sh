#!/usr/bin/env bash
# Upstream evaluation runs (reports/UPSTREAM_EVAL_2026-10-26.md): same config
# chains as scripts/run_stop_grid.sh, strategy path user_data/strategies_up,
# memory gate before each run.
# usage: TIMERANGE=... UNIVERSE=survB|live TAG=... bash scratch/tools/run_up.sh Strategy
cd /d/NostalgiaForInfinity || exit 1
export PYTHONUTF8=1 PYTHONPATH="$(cygpath -w "$PWD/pypatches")" FT_LOWMEM=1
export TEMP='D:\NostalgiaForInfinity\scratch\tmp' TMP='D:\NostalgiaForInfinity\scratch\tmp'
TIMERANGE="${TIMERANGE:-20250216-20260816}"
case "${UNIVERSE:-survB}" in
  survB) UNI=(--config=configs/blacklist-survivorship-test.json --config=configs/pairlist-survivorship-B-real-universe.json) ;;
  live)  UNI=(--config=configs/blacklist-binance.json --config=configs/pairlist-backtest-static-binance-spot-usdt.json) ;;
esac
for S in "$@"; do
  NAME="up-${TAG}-$S"
  dir="user_data/backtest_results/$NAME"
  for attempt in 1 2 3; do
    for i in $(seq 1 120); do
      F=$(powershell.exe -NoProfile -Command "[math]::Floor((Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory/1MB)" | tr -d '\r')
      [ "${F:-0}" -ge "${MIN_FREE_GB:-19}" ] && break; sleep 30
    done
    mkdir -p "$dir"
    echo "=== START $NAME [$TIMERANGE ${UNIVERSE:-survB}] free=${F}GB $(date +%T) ==="
    .venv/Scripts/python.exe scripts/ft_delisted.py backtesting --strategy="$S" --strategy-path=user_data/strategies_up \
      --timerange="$TIMERANGE" --user-data-dir=./user_data \
      --config=configs/exampleconfig.json --config=configs/exampleconfig_secret.json \
      --config=configs/trading_mode-spot.json --config=configs/local-overrides-safe.json "${UNI[@]}" \
      --enable-protections --breakdown month --export trades --cache none \
      --backtest-directory="$dir" > "logs_$NAME.log" 2>&1
    echo "=== DONE $NAME rc=$? $(date +%T) ==="
    ls "$dir"/backtest-result-*.zip > /dev/null 2>&1 && break
    echo "--- no result (attempt $attempt)"
  done
done
