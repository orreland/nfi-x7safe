#!/usr/bin/env bash
# reports/MAINSTREAM_TEST_2026-11-03.md: one queue, one backtest at a time.
cd /d/NostalgiaForInfinity || exit 1
export PYTHONUTF8=1 PYTHONPATH="$(cygpath -w "$PWD/pypatches")" FT_LOWMEM=1
export TEMP='D:\NostalgiaForInfinity\scratch\tmp' TMP='D:\NostalgiaForInfinity\scratch\tmp'
BASE=(--user-data-dir=./user_data --config=configs/exampleconfig.json --config=configs/exampleconfig_secret.json --config=configs/trading_mode-spot.json --config=configs/local-overrides-safe.json --config=configs/blacklist-binance.json --config=configs/pairlist-mainstream14.json)
run() { local name=$1 s=$2 p=$3 tr=$4 dir="user_data/backtest_results/main-$1"
  for i in $(seq 1 120); do F=$(powershell.exe -NoProfile -Command "[math]::Floor((Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory/1MB)" | tr -d '\r'); [ "${F:-0}" -ge 19 ] && break; sleep 30; done
  mkdir -p "$dir"; echo "=== START $name free=${F}GB $(date +%T)"
  .venv/Scripts/python.exe scripts/ft_delisted.py backtesting --strategy="$s" --strategy-path="$p" --timerange="$tr" "${BASE[@]}" \
    --enable-protections --breakdown month --export trades --cache none --backtest-directory="$dir" > "logs_main_$name.log" 2>&1
  echo "=== DONE $name rc=$? $(date +%T)"
}
OURS=user_data/strategies; COMM=user_data/strategies_comm
for w in "P 20261025-20261103" "R 20260830-20261103" "L 20250216-20261103"; do set -- $w
  run "$1-OURS" X7SafeStopHonored $OURS "$2"
  run "$1-X7" NostalgiaForInfinityX7 $COMM "$2"
  run "$1-X8" NostalgiaForInfinityX8 $COMM "$2"
done
echo "=== ALL DONE $(date +%T)"
