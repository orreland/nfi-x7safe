#!/usr/bin/env bash
# reports/ENTRY_POLICY_2026-11-04.md: one backtest at a time. usage: run_entry.sh smoke|all
cd "$(dirname "$0")/../.." || exit 1
export PYTHONUTF8=1 PYTHONPATH="$(cygpath -w "$PWD/pypatches")" FT_LOWMEM=1
export TEMP='D:\NostalgiaForInfinity\scratch\tmp' TMP='D:\NostalgiaForInfinity\scratch\tmp'
BASE=(--user-data-dir=./user_data --config=configs/exampleconfig.json --config=configs/exampleconfig_secret.json --config=configs/trading_mode-spot.json --config=configs/local-overrides-safe.json)
LIVE=(--config=configs/blacklist-binance.json --config=configs/pairlist-backtest-static-binance-spot-usdt.json)
SURV=(--config=configs/blacklist-survivorship-test.json --config=configs/pairlist-survivorship-B-real-universe.json)
run() { # name strategy universe range
  local dir="user_data/backtest_results/entry-$1" rc=1; local -n uni=$3
  ls "$dir"/backtest-result-*.zip >/dev/null 2>&1 && { echo "=== SKIP $1 already done"; return; }
  for attempt in 1 2 3; do
    for i in $(seq 1 240); do F=$(powershell.exe -NoProfile -Command "[math]::Floor((Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory/1MB)" | tr -d '\r'); [ "${F:-0}" -ge 36 ] && break; sleep 30; done
    mkdir -p "$dir"; echo "=== START $1 try=$attempt free=${F}GB $(date +%T)"
    .venv/Scripts/python.exe scripts/ft_delisted.py backtesting --strategy="$2" --strategy-path=user_data/strategies --timerange="$4" "${BASE[@]}" "${uni[@]}" \
      --enable-protections --breakdown month --export trades --cache none --backtest-directory="$dir" > "logs_entry_$1.log" 2>&1
    rc=$?; echo "=== DONE $1 rc=$rc nodata=$(grep -c 'ENTRY-MODEL no 1m' "logs_entry_$1.log") last=$(grep 'ENTRY-MODEL {' "logs_entry_$1.log" | tail -1 | sed 's/.*ENTRY-MODEL //') $(date +%T)"
    [ $rc = 0 ] && break
  done
  [ $rc = 0 ] || FAILED="$FAILED $1"
}
if [ "$1" = smoke ]; then
  run smoke-M X7SafeEntryChase LIVE 20261025-20261103
  run smoke-L0 X7SafeEntryLimit0 LIVE 20261025-20261103
else
  for a in "M X7SafeEntryChase" "C25 X7SafeEntryCap25" "L0 X7SafeEntryLimit0" "L25 X7SafeEntryLimit25" "L50 X7SafeEntryLimit50"; do set -- $a
    run "$1-L" "$2" SURV 20250216-20261103
    run "$1-R" "$2" LIVE 20260830-20261103
  done
  echo "=== ALL DONE failed=[$FAILED ] $(date +%T)"
  [ -z "$FAILED" ]
fi
