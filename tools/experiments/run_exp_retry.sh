#!/usr/bin/env bash
# Re-run X8 long comm runs that hit MemoryError, one at a time, with a higher memory gate.
cd /d/NostalgiaForInfinity || exit 1
export PYTHONUTF8=1 PYTHONPATH="$(cygpath -w "$PWD/pypatches")" FT_LOWMEM=1
export TEMP='D:\NostalgiaForInfinity\scratch\tmp' TMP='D:\NostalgiaForInfinity\scratch\tmp'
BASE=(--user-data-dir=./user_data --config=configs/exampleconfig.json --config=configs/exampleconfig_secret.json --config=configs/trading_mode-spot.json --config=configs/local-overrides-safe.json --config=configs/blacklist-survivorship-test.json --config=configs/pairlist-survivorship-B-real-universe.json)
for spec in "X8S-comm-L X8SafeStopHonored" "X8S-S-comm-L X8SafeSlip" "X8N-comm-L X8SafeNoDoom" "X8-S-comm-L X8CommSlip"; do
  set -- $spec
  dir="user_data/backtest_results/exp-$1"
  for attempt in 1 2 3; do
    for i in $(seq 1 240); do F=$(powershell.exe -NoProfile -Command "[math]::Floor((Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory/1MB)" | tr -d '\r'); [ "${F:-0}" -ge 30 ] && break; sleep 30; done
    mkdir -p "$dir"; echo "=== START $1 try=$attempt free=${F}GB $(date +%T)"
    .venv/Scripts/python.exe scripts/ft_delisted.py backtesting --strategy="$2" --strategy-path=user_data/strategies_x8s --timerange=20250216-20261103 "${BASE[@]}" \
      --enable-protections --breakdown month --export trades --cache none --backtest-directory="$dir" > "logs_exp_$1.log" 2>&1
    rc=$?; echo "=== DONE $1 rc=$rc $(date +%T)"
    [ $rc = 0 ] && break
    sleep 60
  done
done
echo "=== ALL DONE $(date +%T)"
