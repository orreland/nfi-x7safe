#!/usr/bin/env bash
# Re-run a published baseline: bash scripts/run_baseline.sh comm-L-OURS [more...]
# Names: {comm|main}-{P|R|L}-{OURS|X7|X8}. comm = all coins, main = 14 mainstream coins.
# Then check it: python scripts/check_baseline.py comm-L-OURS
# Run one at a time. A long window needs about 19 GB of free virtual memory.
set -uo pipefail
cd "$(dirname "$0")/.."
export PYTHONUTF8=1 FT_LOWMEM=1
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
for run in "$@"; do
  IFS=- read -r uni win arm <<< "$run"
  case "$win" in
    P) range=20261025-20261103 ;;
    R) range=20260830-20261103 ;;
    L) range=20250216-20261103 ;;
    *) echo "bad window in $run"; exit 2 ;;
  esac
  case "$uni-$win" in
    main-*) U=(--config=configs/blacklist-binance.json --config=configs/pairlist-mainstream14.json) ;;
    comm-L) U=(--config=configs/blacklist-survivorship-test.json --config=configs/pairlist-survivorship-B-real-universe.json) ;;
    comm-*) U=(--config=configs/blacklist-binance.json --config=configs/pairlist-backtest-static-binance-spot-usdt.json) ;;
    *) echo "bad universe in $run"; exit 2 ;;
  esac
  case "$arm" in
    OURS) S=X7SafeStopHonored; P=user_data/strategies ;;
    X7) S=NostalgiaForInfinityX7; P=user_data/strategies_comm ;;
    X8) S=NostalgiaForInfinityX8; P=user_data/strategies_comm ;;
    *) echo "bad arm in $run"; exit 2 ;;
  esac
  dir="user_data/backtest_results/$run"
  mkdir -p "$dir"
  echo "=== $run: $S $range"
  "$PY" scripts/ft_delisted.py backtesting --strategy="$S" --strategy-path="$P" --timerange="$range" "${BASE[@]}" "${U[@]}" \
    --enable-protections --breakdown month --export trades --cache none --backtest-directory="$dir" > "logs_$run.log" 2>&1
  echo "=== $run rc=$? (log: logs_$run.log)"
done
